"""Validated image attachment storage for chat messages."""

import base64
import hashlib
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass, asdict
from pathlib import Path

from .chat_repository import DEFAULT_DB


MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS_PER_MESSAGE = 6
IMAGE_SIGNATURES = {
    "image/png": (b"\x89PNG\r\n\x1a\n", ".png"),
    "image/jpeg": (b"\xff\xd8\xff", ".jpg"),
    "image/gif": (b"GIF8", ".gif"),
    "image/webp": (b"RIFF", ".webp"),
}


@dataclass(slots=True)
class Attachment:
    id: str
    thread_id: str
    message_id: int | None
    relative_path: str
    mime_type: str
    original_name: str
    size_bytes: int
    sha256: str
    created_at: str = ""

    def public(self) -> dict:
        data = asdict(self)
        data.pop("relative_path", None)
        data["url"] = f"/api/chat/attachments/{self.id}/content"
        return data


class AttachmentService:
    def __init__(self, db_path: Path = DEFAULT_DB, storage_root: Path | None = None,
                 prune_orphans: bool = False):
        self.db_path = Path(db_path)
        self.storage_root = storage_root or self.db_path.parent / "attachments"
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self._initialize()
        if prune_orphans:
            self._prune_orphan_files()

    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self):
        with closing(self._connect()) as connection, connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    message_id INTEGER,
                    relative_path TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE,
                    FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE CASCADE
                )
            """)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_attachments_message ON attachments(message_id, id)"
            )

    def _prune_orphan_files(self) -> None:
        with closing(self._connect()) as connection:
            referenced = {
                row["relative_path"] for row in connection.execute(
                    "SELECT relative_path FROM attachments"
                ).fetchall()
            }
        for path in self.storage_root.rglob("*"):
            if path.is_file() and path.relative_to(self.storage_root).as_posix() not in referenced:
                path.unlink(missing_ok=True)

    @staticmethod
    def _row(row) -> Attachment:
        return Attachment(**dict(row))

    @staticmethod
    def _detect_type(data: bytes) -> tuple[str, str]:
        for mime, (signature, extension) in IMAGE_SIGNATURES.items():
            if data.startswith(signature):
                if mime == "image/webp" and data[8:12] != b"WEBP":
                    continue
                return mime, extension
        raise ValueError("仅支持 PNG、JPEG、WebP 和 GIF 图片。")

    def save_upload(self, thread_id: str, original_name: str, data: bytes) -> Attachment:
        if not data:
            raise ValueError("图片内容为空。")
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("单张图片不能超过 10 MB。")
        mime_type, extension = self._detect_type(data)
        attachment_id = uuid.uuid4().hex
        relative_path = f"{attachment_id[:2]}/{attachment_id}{extension}"
        target = self.storage_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        attachment = Attachment(
            id=attachment_id, thread_id=thread_id, message_id=None,
            relative_path=relative_path, mime_type=mime_type,
            original_name=Path(original_name or f"image{extension}").name[:255],
            size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
        )
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    "INSERT INTO attachments "
                    "(id,thread_id,message_id,relative_path,mime_type,original_name,size_bytes,sha256) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (attachment.id, attachment.thread_id, None, attachment.relative_path,
                     attachment.mime_type, attachment.original_name, attachment.size_bytes,
                     attachment.sha256),
                )
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return attachment

    def get(self, attachment_id: str) -> Attachment | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM attachments WHERE id = ?", (attachment_id,)
            ).fetchone()
        return self._row(row) if row else None

    def delete_unbound(self, attachment_id: str, thread_id: str) -> bool:
        item = self.get(attachment_id)
        if not item or item.thread_id != thread_id or item.message_id is not None:
            return False
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "DELETE FROM attachments WHERE id = ? AND thread_id = ? AND message_id IS NULL",
                (attachment_id, thread_id),
            )
        if cursor.rowcount:
            self.path_for(item).unlink(missing_ok=True)
        return bool(cursor.rowcount)

    def for_message(self, message_id: int) -> list[Attachment]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM attachments WHERE message_id = ? ORDER BY created_at, id",
                (message_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def for_thread(self, thread_id: str) -> list[Attachment]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM attachments WHERE thread_id = ?", (thread_id,)
            ).fetchall()
        return [self._row(row) for row in rows]

    def delete_files(self, items: list[Attachment]) -> None:
        for item in items:
            self.path_for(item).unlink(missing_ok=True)

    def validate_for_thread(self, thread_id: str, attachment_ids: list[str]) -> list[Attachment]:
        ids = list(dict.fromkeys(attachment_ids))
        if len(ids) > MAX_ATTACHMENTS_PER_MESSAGE:
            raise ValueError("每条消息最多发送 6 张图片。")
        attachments = []
        for attachment_id in ids:
            item = self.get(attachment_id)
            if not item or item.thread_id != thread_id or item.message_id is not None:
                raise ValueError(f"附件 {attachment_id} 不存在、已使用或不属于当前对话。")
            attachments.append(item)
        return attachments

    def bind(self, message_id: int, attachments: list[Attachment]) -> None:
        if not attachments:
            return
        with closing(self._connect()) as connection, connection:
            for item in attachments:
                cursor = connection.execute(
                    "UPDATE attachments SET message_id = ? WHERE id = ? AND message_id IS NULL",
                    (message_id, item.id),
                )
                if cursor.rowcount != 1:
                    raise ValueError(f"附件 {item.id} 已被其他消息使用。")

    def path_for(self, attachment: Attachment) -> Path:
        target = (self.storage_root / attachment.relative_path).resolve()
        root = self.storage_root.resolve()
        if target != root and root not in target.parents:
            raise ValueError("附件路径无效。")
        return target

    def multimodal_content(self, text: str, attachments: list[Attachment]) -> str | list[dict]:
        if not attachments:
            return text
        blocks: list[dict] = [{"type": "text", "text": text or "请分析这些图片。"}]
        for item in attachments:
            encoded = base64.b64encode(self.path_for(item).read_bytes()).decode("ascii")
            blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:{item.mime_type};base64,{encoded}"},
            })
        return blocks
