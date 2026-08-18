"""Resolve packaged resources separately from writable application data."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.environ.get("MY_AGENT_HOME", PACKAGE_ROOT)).expanduser().resolve()
DATA_DIR = RUNTIME_ROOT / "data"
SKILLS_DIR = RUNTIME_ROOT / "skills"
ENV_FILE = RUNTIME_ROOT / ".env"
CONFIG_FILE = RUNTIME_ROOT / "config.yaml"


def initialize_runtime() -> None:
    """Create writable state and seed packaged defaults on first launch."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "attachments").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "agent-runs").mkdir(parents=True, exist_ok=True)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    packaged_config = PACKAGE_ROOT / "config.yaml"
    if not CONFIG_FILE.exists() and packaged_config.is_file():
        shutil.copy2(packaged_config, CONFIG_FILE)

    packaged_skills = PACKAGE_ROOT / "skills"
    if packaged_skills.resolve() != SKILLS_DIR.resolve() and packaged_skills.is_dir():
        for source in packaged_skills.iterdir():
            if not source.is_dir() or not (source / "SKILL.md").is_file():
                continue
            target = SKILLS_DIR / source.name
            if target.exists():
                continue
            shutil.copytree(source, target)
