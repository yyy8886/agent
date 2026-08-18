# api_profile_repository.py — SQLite 持久化层
# =============================================================================
# 本文件负责 ApiProfile 的数据库存取，是"数据访问层"（DAO / Repository）。
#
# 职责：
#   1. _initialize() — 首次运行时自动建表 api_profiles + 唯一索引（最多一个默认配置）
#   2. list() / get() — 读取所有配置 / 按 ID 读取单个
#   3. save()         — INSERT OR UPDATE（UPSERT），同时维护 is_default 唯一约束
#   4. delete()       — 按 ID 删除
#   5. set_default()  — 先取消所有默认，再把指定配置设为默认
#
# 存储位置：my_agent_next/data/app.db（SQLite 文件，不提交密钥）
# 表结构：api_profiles（14 个字段，含 created_at / updated_at 自动时间戳）
#
# 项目中的位置：
#   ApiProfileService → ApiProfileRepository → SQLite
#   业务逻辑          → 数据访问             → 数据库"""

import sqlite3
from contextlib import closing
from pathlib import Path

from .runtime_paths import DATA_DIR

from .api_profile import ApiProfile


DEFAULT_DB = DATA_DIR / "app.db"


class ApiProfileRepository:
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
                CREATE TABLE IF NOT EXISTS api_profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    base_url TEXT NOT NULL DEFAULT '',
                    api_key_env TEXT,
                    temperature REAL NOT NULL,
                    timeout_seconds INTEGER NOT NULL,
                    max_retries INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS one_default_api_profile "
                "ON api_profiles(is_default) WHERE is_default = 1"
            )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ApiProfile:
        return ApiProfile(
            id=row["id"], name=row["name"], provider=row["provider"], model=row["model"],
            base_url=row["base_url"], api_key_env=row["api_key_env"],
            temperature=row["temperature"], timeout_seconds=row["timeout_seconds"],
            max_retries=row["max_retries"], enabled=bool(row["enabled"]),
            is_default=bool(row["is_default"]),
        )

    def list(self) -> list[ApiProfile]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM api_profiles ORDER BY name, id").fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, profile_id: str) -> ApiProfile | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM api_profiles WHERE id = ?", (profile_id,)).fetchone()
        return self._from_row(row) if row else None

    def save(self, profile: ApiProfile) -> None:
        with closing(self._connect()) as connection, connection:
            if profile.is_default:
                connection.execute("UPDATE api_profiles SET is_default = 0 WHERE id <> ?", (profile.id,))
            connection.execute(
                """
                INSERT INTO api_profiles
                (id,name,provider,model,base_url,api_key_env,temperature,timeout_seconds,max_retries,enabled,is_default)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                  name=excluded.name, provider=excluded.provider, model=excluded.model,
                  base_url=excluded.base_url, api_key_env=excluded.api_key_env,
                  temperature=excluded.temperature, timeout_seconds=excluded.timeout_seconds,
                  max_retries=excluded.max_retries, enabled=excluded.enabled,
                  is_default=excluded.is_default, updated_at=CURRENT_TIMESTAMP
                """,
                (profile.id, profile.name, profile.provider, profile.model, profile.base_url,
                 profile.api_key_env, profile.temperature, profile.timeout_seconds,
                 profile.max_retries, int(profile.enabled), int(profile.is_default)),
            )

    def delete(self, profile_id: str) -> bool:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute("DELETE FROM api_profiles WHERE id = ?", (profile_id,))
        return cursor.rowcount > 0

    def set_default(self, profile_id: str) -> None:
        with closing(self._connect()) as connection, connection:
            exists = connection.execute("SELECT 1 FROM api_profiles WHERE id = ? AND enabled = 1", (profile_id,)).fetchone()
            if not exists:
                raise ValueError("只有存在且启用的配置可以设为默认。")
            connection.execute("UPDATE api_profiles SET is_default = 0")
            connection.execute("UPDATE api_profiles SET is_default = 1 WHERE id = ?", (profile_id,))
