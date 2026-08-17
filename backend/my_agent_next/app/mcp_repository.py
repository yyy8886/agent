"""SQLite persistence for MCP server configurations and Agent bindings."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .agent_profile_repository import DEFAULT_DB


class McpServerRepository:
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
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS mcp_servers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    transport TEXT NOT NULL DEFAULT 'stdio',
                    command TEXT NOT NULL,
                    args_json TEXT NOT NULL DEFAULT '[]',
                    cwd TEXT NOT NULL DEFAULT '',
                    env_names_json TEXT NOT NULL DEFAULT '[]',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS mcp_agent_bindings (
                    server_id TEXT NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
                    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                    PRIMARY KEY (server_id, agent_id)
                );
                """
            )

    def list(self) -> list[dict]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM mcp_servers ORDER BY name, id"
            ).fetchall()
            bindings = connection.execute(
                "SELECT server_id, agent_id FROM mcp_agent_bindings ORDER BY agent_id"
            ).fetchall()
        by_server: dict[str, list[str]] = {}
        for row in bindings:
            by_server.setdefault(row["server_id"], []).append(row["agent_id"])
        return [self._from_row(row, by_server.get(row["id"], [])) for row in rows]

    def get(self, server_id: str) -> dict | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM mcp_servers WHERE id=?", (server_id,)
            ).fetchone()
            if row is None:
                return None
            agents = [item["agent_id"] for item in connection.execute(
                "SELECT agent_id FROM mcp_agent_bindings WHERE server_id=? ORDER BY agent_id",
                (server_id,),
            ).fetchall()]
        return self._from_row(row, agents)

    def list_for_agent(self, agent_id: str) -> list[dict]:
        return [item for item in self.list() if item["enabled"] and agent_id in item["agent_ids"]]

    def save(self, value: dict) -> dict:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO mcp_servers
                    (id,name,transport,command,args_json,cwd,env_names_json,enabled)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, transport=excluded.transport,
                    command=excluded.command, args_json=excluded.args_json,
                    cwd=excluded.cwd, env_names_json=excluded.env_names_json,
                    enabled=excluded.enabled, updated_at=CURRENT_TIMESTAMP
                """,
                (
                    value["id"], value["name"], value["transport"], value["command"],
                    json.dumps(value["args"], ensure_ascii=False), value["cwd"],
                    json.dumps(value["env_names"], ensure_ascii=False), int(value["enabled"]),
                ),
            )
            connection.execute("DELETE FROM mcp_agent_bindings WHERE server_id=?", (value["id"],))
            connection.executemany(
                "INSERT INTO mcp_agent_bindings(server_id,agent_id) VALUES (?,?)",
                [(value["id"], agent_id) for agent_id in value["agent_ids"]],
            )
        return self.get(value["id"])

    def delete(self, server_id: str) -> bool:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute("DELETE FROM mcp_servers WHERE id=?", (server_id,))
        return cursor.rowcount > 0

    @staticmethod
    def _from_row(row: sqlite3.Row, agent_ids: list[str]) -> dict:
        return {
            "id": row["id"], "name": row["name"], "transport": row["transport"],
            "command": row["command"], "args": json.loads(row["args_json"]),
            "cwd": row["cwd"], "env_names": json.loads(row["env_names_json"]),
            "enabled": bool(row["enabled"]), "agent_ids": list(agent_ids),
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }
