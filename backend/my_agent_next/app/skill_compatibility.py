"""Deterministic, non-executing compatibility scans for installed Skills."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .agent_profile_repository import DEFAULT_DB

SCANNER_VERSION = 4
SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
IGNORED_PARTS = {".git", "__pycache__", "node_modules", ".DS_Store"}
TEXT_SUFFIXES = {".md", ".py", ".ps1", ".sh", ".bat", ".cmd", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".txt"}
COMMANDS = ("python", "python3", "node", "npm", "git", "drawio", "ffmpeg", "pwsh", "powershell", "bash", "curl")


def environment_fingerprint() -> str:
    payload = {
        "system": platform.system().lower(),
        "machine": platform.machine().lower(),
        "python": platform.python_version(),
        "commands": {name: bool(shutil.which(name)) for name in COMMANDS},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def skill_fingerprint(skill_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or any(part in IGNORED_PARTS for part in path.relative_to(skill_dir).parts):
            continue
        relative = path.relative_to(skill_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
    return digest.hexdigest()


class SkillCompatibilityRepository:
    def __init__(self, db_path: Path = DEFAULT_DB):
        self.db_path = Path(db_path)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with closing(self._connect()) as connection, connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS skill_compatibility (
                skill_name TEXT PRIMARY KEY, skill_fingerprint TEXT NOT NULL,
                environment_fingerprint TEXT NOT NULL, scanner_version INTEGER NOT NULL,
                level TEXT NOT NULL, score INTEGER NOT NULL, summary TEXT NOT NULL,
                details_json TEXT NOT NULL, safety_level TEXT NOT NULL,
                scanned_at TEXT NOT NULL, scan_trigger TEXT NOT NULL
            )""")

    def get(self, name: str) -> dict | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM skill_compatibility WHERE skill_name=?", (name,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["issues"] = json.loads(data.pop("details_json"))
        return data

    def save(self, report: dict) -> None:
        values = dict(report)
        values["details_json"] = json.dumps(values.pop("issues"), ensure_ascii=False)
        columns = ("skill_name", "skill_fingerprint", "environment_fingerprint", "scanner_version", "level", "score", "summary", "details_json", "safety_level", "scanned_at", "scan_trigger")
        with closing(self._connect()) as connection, connection:
            connection.execute(
                f"INSERT OR REPLACE INTO skill_compatibility ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                tuple(values[column] for column in columns),
            )


def _read_texts(skill_dir: Path) -> tuple[str, dict[str, str]]:
    chunks, files = [], {}
    for path in sorted(skill_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES and path.stat().st_size <= 1_000_000:
            relative = path.relative_to(skill_dir).as_posix()
            content = path.read_text(encoding="utf-8", errors="replace")
            files[relative] = content
            chunks.append(content)
    return "\n".join(chunks), files


def _without_urls(text: str) -> str:
    """Remove network URLs before looking for local filesystem paths."""
    return re.sub(r"https?://[^\s<>()`'\"]+", "", text, flags=re.I)


def _active_platform_tokens(files: dict[str, str]) -> list[str]:
    """Return platform conventions used as requirements, not warnings/examples."""
    hits = set()
    negative = re.compile(
        r"(?:never|do not|don't|must not|not from|avoid|instead of|禁止|不要|不得|避免)", re.I
    )
    for relative, content in files.items():
        lines = content.splitlines()
        for index, line in enumerate(lines):
            folded = line.casefold()
            context_lines = lines[max(0, index - 1):index + 1]
            if any(negative.search(context_line) for context_line in context_lines):
                continue
            for token in ("$CODEX_HOME", "~/.codex"):
                if token.casefold() in folded:
                    hits.add(token)
    # A Codex plugin manifest is a genuine output contract, wherever documented.
    if any(".codex-plugin/plugin.json" in content for content in files.values()):
        hits.add(".codex-plugin")
    # OpenClaw metadata is declarative interoperability metadata, not a runtime dependency.
    return sorted(hits)


def _hardcoded_absolute_paths(files: dict[str, str]) -> list[str]:
    """Find machine paths in executable/config files; ignore prose examples."""
    executable_suffixes = {".py", ".ps1", ".sh", ".bat", ".cmd", ".js", ".ts"}
    matches = set()
    pattern = re.compile(
        r"(?:(?<![A-Za-z0-9_])[A-Za-z]:\\[^\s`'\"]+|"
        r"(?<![A-Za-z0-9_])[A-Za-z]:/(?!/)[^\s`'\"]+|"
        r"/(?:home|Users|mnt)/[^\s`'\"]+)"
    )
    for relative, content in files.items():
        if Path(relative).suffix.lower() not in executable_suffixes:
            continue
        matches.update(pattern.findall(_without_urls(content)))
    return sorted(matches)


def _required_commands(files: dict[str, str]) -> list[str]:
    """Infer commands from executable code and explicit dependency declarations."""
    executable_suffixes = {".py", ".ps1", ".sh", ".bat", ".cmd", ".js", ".ts"}
    evidence = "\n".join(
        content for relative, content in files.items()
        if Path(relative).suffix.lower() in executable_suffixes
    )
    skill_md = files.get("SKILL.md", "")
    declarations = "\n".join(
        line for line in skill_md.splitlines()
        if re.search(
            r"requires_tools|required command|requires.*bins|anyBins|"
            r"(?:use|run|execute|invoke|使用|运行|执行)\s+",
            line, re.I,
        )
    )
    searchable = evidence + "\n" + declarations
    return [
        command for command in COMMANDS
        if re.search(rf"(?<![\w-]){re.escape(command)}(?![\w-])", searchable, re.I)
    ]


def _missing_commands(required: list[str]) -> list[str]:
    """Resolve alternative command families instead of requiring every alias."""
    missing = [command for command in required if not shutil.which(command)]
    for family in ({"python", "python3"}, {"pwsh", "powershell"}, {"drawio", "draw.io"}):
        mentioned = family.intersection(required)
        if mentioned and any(shutil.which(command) for command in family):
            missing = [command for command in missing if command not in family]
    return missing


def scan_skill(name: str, trigger: str = "manual", skills_dir: Path = SKILLS_DIR, repository: SkillCompatibilityRepository | None = None) -> dict:
    skill_dir = (Path(skills_dir) / name).resolve()
    try:
        skill_dir.relative_to(Path(skills_dir).resolve())
    except ValueError:
        raise ValueError("Invalid Skill path")
    if not (skill_dir / "SKILL.md").is_file():
        raise FileNotFoundError(name)
    before = skill_fingerprint(skill_dir)
    text, files = _read_texts(skill_dir)
    issues, penalty, safety = [], 0, "normal"

    def add(code: str, severity: str, message: str, suggestion: str, points: int):
        nonlocal penalty
        issues.append({"code": code, "severity": severity, "message": message, "suggestion": suggestion})
        penalty += points

    if not re.match(r"^---\s*\n.*?\n---", (skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="replace"), re.S):
        add("invalid_frontmatter", "error", "SKILL.md frontmatter 无效", "修复 YAML frontmatter", 60)
    platform_hits = _active_platform_tokens(files)
    if platform_hits:
        add("platform_specific", "warning", "发现平台专属约定：" + "、".join(platform_hits), "检查并替换为本应用支持的工具和相对路径", 20)
    absolute = _hardcoded_absolute_paths(files)
    if absolute:
        add("absolute_path", "warning", f"发现 {len(absolute)} 个机器相关绝对路径", "改用 Skill 目录相对路径", 15)
    mentioned = _required_commands(files)
    missing = _missing_commands(mentioned)
    if missing:
        add("missing_command", "warning", "当前环境缺少命令：" + "、".join(missing), "安装依赖或提供当前平台替代命令", min(35, 10 * len(missing)))
    suffixes = {Path(item).suffix.lower() for item in files}
    current = platform.system().lower()
    if current == "windows" and ".sh" in suffixes and not shutil.which("bash"):
        add("unsupported_script", "error", "包含 Shell 脚本但当前 Windows 环境没有 Bash", "提供 PowerShell/Python 版本", 35)
    if current != "windows" and suffixes.intersection({".ps1", ".bat", ".cmd"}) and not shutil.which("pwsh"):
        add("unsupported_script", "error", "包含 Windows 脚本但当前环境没有 PowerShell", "提供 Bash/Python 版本", 35)
    if re.search(r"(?:curl|wget).*(?:\||;).*?(?:sh|bash)|Invoke-Expression|rm\s+-rf", text, re.I):
        safety = "high"
    elif re.search(r"pip install|npm install|download|Invoke-WebRequest", text, re.I):
        safety = "attention"
    after = skill_fingerprint(skill_dir)
    if before != after:
        raise RuntimeError("Skill changed during scan")
    score = max(0, 100 - penalty)
    level = "green" if score == 100 else "yellow" if score >= 50 else "red"
    summary = {"green": "当前环境未发现兼容障碍", "yellow": "核心能力可能可用，但需要配置或适配", "red": "存在核心兼容障碍，需要较大改造"}[level]
    report = {"skill_name": name, "skill_fingerprint": before, "environment_fingerprint": environment_fingerprint(), "scanner_version": SCANNER_VERSION, "level": level, "score": score, "summary": summary, "issues": issues, "safety_level": safety, "scanned_at": datetime.now(timezone.utc).isoformat(), "scan_trigger": trigger}
    (repository or SkillCompatibilityRepository()).save(report)
    return {**report, "status": "ready"}


def compatibility_status(name: str, skills_dir: Path = SKILLS_DIR, repository: SkillCompatibilityRepository | None = None) -> dict:
    skill_dir = Path(skills_dir) / name
    if not (skill_dir / "SKILL.md").is_file():
        return {"status": "missing", "level": None, "summary": "Skill 文件缺失"}
    stored = (repository or SkillCompatibilityRepository()).get(name)
    if not stored:
        return {"status": "unscanned", "level": None, "summary": "尚未扫描"}
    stale = stored["skill_fingerprint"] != skill_fingerprint(skill_dir) or stored["environment_fingerprint"] != environment_fingerprint() or stored["scanner_version"] != SCANNER_VERSION
    return {**stored, "status": "stale" if stale else "ready"}
