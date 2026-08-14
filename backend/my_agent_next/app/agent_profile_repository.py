# agent_profile_repository.py — Agent 的 SQLite 持久化层
# =============================================================================
# 本文件负责 AgentProfile 的数据库存取，与 ApiProfileRepository 平行。
#
# 存储位置：my_agent_next/data/app.db → agents 表
# 表结构：id / name / role / persona / model_profile_id / skills(JSON) / enabled / timestamps
#
# skills 以 JSON 数组形式存入 TEXT 字段，便于 SQLite 直接读写。
# 项目中的位置：
#   AgentProfileService → AgentProfileRepository → SQLite agents 表"""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .agent_profile import AgentProfile


DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "app.db"


class AgentProfileRepository:
    def __init__(self, db_path: Path = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT '',
                    persona TEXT NOT NULL DEFAULT '',
                    model_profile_id TEXT NOT NULL DEFAULT '',
                    skills TEXT NOT NULL DEFAULT '[]',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> AgentProfile:
        return AgentProfile(
            id=row["id"], name=row["name"], role=row["role"],
            persona=row["persona"], model_profile_id=row["model_profile_id"],
            skills=json.loads(row["skills"]), enabled=bool(row["enabled"]),
        )

    def list(self) -> list[AgentProfile]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM agents ORDER BY name, id").fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, agent_id: str) -> AgentProfile | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        return self._from_row(row) if row else None

    def save(self, profile: AgentProfile) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO agents
                (id, name, role, persona, model_profile_id, skills, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  name=excluded.name, role=excluded.role, persona=excluded.persona,
                  model_profile_id=excluded.model_profile_id, skills=excluded.skills,
                  enabled=excluded.enabled, updated_at=CURRENT_TIMESTAMP
                """,
                (profile.id, profile.name, profile.role, profile.persona,
                 profile.model_profile_id, json.dumps(profile.skills, ensure_ascii=False),
                 int(profile.enabled)),
            )

    def add_skill(self, agent_id: str, skill_name: str) -> bool:
        """Atomically append a Skill binding without overwriting other Agent fields."""
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT skills FROM agents WHERE id = ?", (agent_id,)
            ).fetchone()
            if row is None:
                return False
            skills = json.loads(row["skills"])
            if skill_name in skills:
                return False
            skills.append(skill_name)
            connection.execute(
                """
                UPDATE agents
                SET skills = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (json.dumps(skills, ensure_ascii=False), agent_id),
            )
        return True

    def delete(self, agent_id: str) -> bool:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        return cursor.rowcount > 0
