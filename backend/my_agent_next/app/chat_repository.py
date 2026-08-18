# chat_repository.py — 对话线程与消息的 SQLite 持久化层
# =============================================================================
# 本文件负责 chat_threads 和 chat_messages 两张表的存取，
# 以及 compact（自动摘要压缩）逻辑。
#
# 表结构：
#   chat_threads  — id / agent_id / title / summary / created_at / updated_at
#   chat_messages — id / thread_id / role / content / created_at
#
# Compact 策略：
#   当线程消息数 > max_context_messages 时，取最老的 (总数 - keep_recent) 条消息，
#   调用模型总结成一段中文摘要，存入 chat_threads.summary，然后删除老消息。
#
# 项目中的位置：
#   chat_api.py → chat_repository.py → SQLite chat_threads / chat_messages"""

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .runtime_paths import DATA_DIR

DEFAULT_DB = DATA_DIR / "app.db"


@dataclass(slots=True)
class ChatMessage:
    id: int
    thread_id: str
    role: str  # "user" | "assistant"
    content: str
    created_at: str = ""


class ChatRepository:
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
                CREATE TABLE IF NOT EXISTS chat_threads (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_messages_thread "
                "ON chat_messages(thread_id, id)"
            )

    # ── 线程 ─────────────────────────────────────────────────────────────────

    def list_threads(self, agent_id: str) -> list[dict]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM chat_threads WHERE agent_id = ? ORDER BY updated_at DESC",
                (agent_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_thread(self, thread_id: str) -> dict | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM chat_threads WHERE id = ?", (thread_id,)
            ).fetchone()
        return dict(row) if row else None

    def create_thread(self, thread_id: str, agent_id: str, title: str = "") -> dict:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO chat_threads (id, agent_id, title) VALUES (?, ?, ?)",
                (thread_id, agent_id, title),
            )
        return self.get_thread(thread_id)

    def update_thread_title(self, thread_id: str, title: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE chat_threads SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (title, thread_id),
            )

    def update_thread_summary(self, thread_id: str, summary: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE chat_threads SET summary = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (summary, thread_id),
            )

    def touch_thread(self, thread_id: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE chat_threads SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (thread_id,),
            )

    def delete_thread(self, thread_id: str) -> bool:
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            cursor = connection.execute(
                "DELETE FROM chat_threads WHERE id = ?", (thread_id,)
            )
        return cursor.rowcount > 0

    # ── 消息 ─────────────────────────────────────────────────────────────────

    def get_messages(self, thread_id: str, limit: int = 0) -> list[ChatMessage]:
        with closing(self._connect()) as connection:
            query = "SELECT * FROM chat_messages WHERE thread_id = ? ORDER BY id"
            if limit > 0:
                # 取最近 limit 条
                rows = connection.execute(
                    "SELECT * FROM (SELECT * FROM chat_messages WHERE thread_id = ? ORDER BY id DESC LIMIT ?) ORDER BY id",
                    (thread_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(query, (thread_id,)).fetchall()
        return [ChatMessage(id=r["id"], thread_id=r["thread_id"],
                            role=r["role"], content=r["content"],
                            created_at=r["created_at"]) for r in rows]

    def save_message(self, thread_id: str, role: str, content: str) -> ChatMessage:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "INSERT INTO chat_messages (thread_id, role, content) VALUES (?, ?, ?)",
                (thread_id, role, content),
            )
        return ChatMessage(id=cursor.lastrowid, thread_id=thread_id,
                           role=role, content=content)

    def count_messages(self, thread_id: str) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS cnt FROM chat_messages WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        return row["cnt"] if row else 0

    def delete_oldest_messages(self, thread_id: str, count: int) -> None:
        """删除线程中最老的 count 条消息。"""
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "DELETE FROM chat_messages WHERE id IN ("
                "SELECT id FROM chat_messages WHERE thread_id = ? ORDER BY id LIMIT ?"
                ")", (thread_id, count),
            )

    def enforce_message_limit(self, thread_id: str, limit: int) -> None:
        """如果消息数超过 limit，FIFO 删除最老的。"""
        count = self.count_messages(thread_id)
        if count > limit:
            self.delete_oldest_messages(thread_id, count - limit)

    # ── Compact ──────────────────────────────────────────────────────────────

    def should_compact(self, thread_id: str, threshold: int) -> bool:
        """判断线程消息数是否超过 threshold，需要压缩。"""
        return self.count_messages(thread_id) > threshold

    def compact(self, thread_id: str, keep_recent: int) -> str | None:
        """
        压缩线程的旧消息为摘要。

        取最老的 (总数 - keep_recent) 条消息，组成摘要提示词，
        但不会直接调用 LLM——只返回待总结的文本，由调用方调 LLM。
        """
        total = self.count_messages(thread_id)
        if total <= keep_recent:
            return None

        remove_count = total - keep_recent
        old_messages = self.get_messages(thread_id, limit=total)[:remove_count]
        if not old_messages:
            return None

        # 构建摘要提示词
        lines = [f"{'用户' if m.role == 'user' else 'AI'}：{m.content}" for m in old_messages]
        return "以下是对话的早期记录，请用一段中文简洁总结关键信息和结论，不超过 300 字：\n\n" + "\n".join(lines)

    def apply_compact(self, thread_id: str, summary: str, keep_recent: int) -> None:
        """应用 compact：更新 summary，删除已压缩的旧消息。"""
        self.update_thread_summary(thread_id, summary)
        total = self.count_messages(thread_id)
        remove_count = total - keep_recent
        if remove_count > 0:
            self.delete_oldest_messages(thread_id, remove_count)
