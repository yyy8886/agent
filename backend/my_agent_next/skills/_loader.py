"""Load Skills through a rebuildable persistent metadata index.

SKILL.md remains the source of truth. ``index.json`` stores only metadata and
content fingerprints; Agent bindings remain the authorization boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).resolve().parent
INDEX_PATH = SKILLS_DIR / "index.json"
INDEX_VERSION = 1


@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    path: Path
    content: str


def _skill_directories(skills_dir: Path) -> list[Path]:
    return [
        entry for entry in sorted(skills_dir.iterdir())
        if entry.is_dir()
        and not entry.name.startswith(("_", "."))
        and (entry / "SKILL.md").is_file()
    ]


def _read_skill(skill_dir: Path) -> tuple[dict, str, str] | None:
    md_file = skill_dir / "SKILL.md"
    if not md_file.is_file():
        return None
    raw = md_file.read_bytes()
    text = raw.decode("utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not match:
        return None
    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(frontmatter, dict):
        return None
    return frontmatter, match.group(2).strip(), hashlib.sha256(raw).hexdigest()


def _build_index_data(skills_dir: Path) -> dict:
    entries = []
    for skill_dir in _skill_directories(skills_dir):
        parsed = _read_skill(skill_dir)
        if parsed is None:
            continue
        frontmatter, _, digest = parsed
        entries.append({
            "directory": skill_dir.name,
            "name": str(frontmatter.get("name") or skill_dir.name),
            "description": str(frontmatter.get("description") or ""),
            "sha256": digest,
        })
    return {"version": INDEX_VERSION, "skills": entries}


def _write_index(data: dict, index_path: Path) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{index_path.name}.", suffix=".tmp", dir=index_path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, index_path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def ensure_index(
    skills_dir: Path = SKILLS_DIR, index_path: Path | None = None
) -> dict:
    """Return a current index, rebuilding it atomically when sources change."""
    skills_dir = Path(skills_dir)
    index_path = Path(index_path) if index_path else skills_dir / "index.json"
    current = _build_index_data(skills_dir)
    try:
        stored = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        stored = None
    if stored != current:
        _write_index(current, index_path)
    return current


def rebuild_index(
    skills_dir: Path = SKILLS_DIR, index_path: Path | None = None
) -> dict:
    """Force an atomic rebuild and return the new index data."""
    skills_dir = Path(skills_dir)
    index_path = Path(index_path) if index_path else skills_dir / "index.json"
    data = _build_index_data(skills_dir)
    _write_index(data, index_path)
    return data


def _parse_skill(skill_dir: Path) -> SkillInfo | None:
    parsed = _read_skill(skill_dir)
    if parsed is None:
        return None
    frontmatter, body, _ = parsed
    return SkillInfo(
        name=str(frontmatter.get("name") or skill_dir.name),
        description=str(frontmatter.get("description") or ""),
        path=skill_dir,
        content=body,
    )


def load_all() -> list[SkillInfo]:
    index = ensure_index()
    return [
        info for entry in index["skills"]
        if (info := _parse_skill(SKILLS_DIR / entry["directory"])) is not None
    ]


def get(name: str) -> SkillInfo | None:
    index = ensure_index()
    entry = next(
        (item for item in index["skills"] if name in (item["directory"], item["name"])),
        None,
    )
    return _parse_skill(SKILLS_DIR / entry["directory"]) if entry else None


def available_skill_choices() -> list[dict]:
    """Read lightweight metadata directly from the persistent index."""
    from my_agent_next.app.skill_compatibility import compatibility_status, scan_skill

    def compatibility(directory: str) -> dict:
        status = compatibility_status(directory)
        if status["status"] == "unscanned":
            try:
                return scan_skill(directory, trigger="discovery")
            except (OSError, ValueError, RuntimeError):
                return status
        return status

    return [
        {
            "name": item["directory"],
            "display_name": item["name"],
            "description": item["description"],
            "compatibility": compatibility(item["directory"]),
        }
        for item in ensure_index()["skills"]
    ]
