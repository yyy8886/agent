"""Agent definitions, persona settings, and per-Agent Skill bindings."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = Path(__file__).resolve().parent / "data" / "agents.json"
CONFIG_FILE = BACKEND_DIR / "config.yaml"
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")


class AgentManager:
    def _load(self) -> dict:
        if not DATA_FILE.exists():
            return {"agents": {}}
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list(self) -> list[dict]:
        return list(self._load().get("agents", {}).values())

    def ids(self) -> set[str]:
        return {item["id"] for item in self.list()}

    def save(self, payload: dict) -> dict:
        agent_id = str(payload.get("id", "")).strip()
        if not ID_PATTERN.fullmatch(agent_id):
            raise ValueError("Agent ID 只能使用小写字母、数字、下划线和连字符。")
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("Agent 名称不能为空。")
        stored = {
            "id": agent_id,
            "name": name,
            "role": str(payload.get("role", "")).strip(),
            "persona": str(payload.get("persona", "")).strip(),
            "skills": sorted({str(skill) for skill in payload.get("skills", []) if str(skill).strip()}),
            "enabled": bool(payload.get("enabled", True)),
        }
        data = self._load()
        data.setdefault("agents", {})[agent_id] = stored
        self._save(data)
        self._sync_skill_config(agent_id, stored["skills"])
        return stored

    def delete(self, agent_id: str) -> bool:
        data = self._load()
        removed = data.setdefault("agents", {}).pop(agent_id, None)
        self._save(data)
        if removed:
            self._remove_skill_config(agent_id)
        return removed is not None

    def _read_config(self) -> dict:
        return yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))

    def _write_config(self, config: dict) -> None:
        CONFIG_FILE.write_text(
            yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def _sync_skill_config(self, agent_id: str, skills: list[str]) -> None:
        config = self._read_config()
        config.setdefault("agent_skills", {}).setdefault("agents", {})[agent_id] = skills
        self._write_config(config)

    def _remove_skill_config(self, agent_id: str) -> None:
        config = self._read_config()
        config.setdefault("agent_skills", {}).setdefault("agents", {}).pop(agent_id, None)
        self._write_config(config)
