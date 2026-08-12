# user_memory_repository.py — 用户记忆 SQLite 持久化层
# =============================================================================
# 存储关于用户的长期事实（偏好、背景、习惯等），跨对话线程共享。
#
# 表：user_memories — id / fact / created_at
# 每个 fact 是一句话（如"用户叫小王"、"用户喜欢简洁回答"）
#
# 项目中的位置（三层架构）：
#   user_memory_service.py → user_memory_repository.py → SQLite user_memories
# =============================================================================

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "app.db"


@dataclass(slots=True)
class UserMemory:
    id: int
    fact: str
    created_at: str = ""


class UserMemoryRepository:
    def __init__(self, db_path: Path = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path))
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def list_all(self) -> list[UserMemory]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM user_memories ORDER BY id"
            ).fetchall()
        return [UserMemory(id=r["id"], fact=r["fact"], created_at=r["created_at"])
                for r in rows]

    def add_if_new(self, fact: str) -> UserMemory | None:
        """只插入不重复的事实（忽略大小写和前后空格）。"""
        normalized = fact.strip()
        if not normalized:
            return None
        with closing(self._connect()) as connection:
            existing = connection.execute(
                "SELECT 1 FROM user_memories WHERE LOWER(fact) = LOWER(?)",
                (normalized,),
            ).fetchone()
            if existing:
                return None
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "INSERT INTO user_memories (fact) VALUES (?)", (normalized,)
            )
        return UserMemory(id=cursor.lastrowid, fact=normalized)

    def delete(self, memory_id: int) -> bool:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "DELETE FROM user_memories WHERE id = ?", (memory_id,)
            )
        return cursor.rowcount > 0

    def clear_all(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM user_memories")
