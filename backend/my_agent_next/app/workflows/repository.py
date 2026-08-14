"""SQLite persistence for editable workflow drafts."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from .model import WorkflowDraft, WorkflowDraftDependency


DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "app.db"


class WorkflowRepository:
    def __init__(self, db_path: str | Path = DEFAULT_DB) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _init_db(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    draft_source TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS workflow_draft_dependencies (
                    workflow_id TEXT NOT NULL,
                    dependency_key TEXT NOT NULL,
                    target_workflow_id TEXT NOT NULL,
                    PRIMARY KEY (workflow_id, dependency_key),
                    CHECK (workflow_id <> target_workflow_id),
                    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_workflow_id) REFERENCES workflows(id) ON DELETE RESTRICT
                );
                """
            )
            connection.commit()

    def list(self) -> list[WorkflowDraft]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM workflows ORDER BY updated_at DESC, id"
            ).fetchall()
            dependencies = self._all_dependencies(connection)
        return [self._from_row(row, dependencies.get(row["id"], ())) for row in rows]

    def get(self, workflow_id: str) -> WorkflowDraft | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM workflows WHERE id = ?", (workflow_id,)
            ).fetchone()
            if row is None:
                return None
            dependencies = self._dependencies(connection, workflow_id)
        return self._from_row(row, dependencies)

    def save(self, draft: WorkflowDraft, *, create: bool) -> WorkflowDraft:
        with closing(self._connect()) as connection:
            try:
                connection.execute("BEGIN")
                if create:
                    connection.execute(
                        "INSERT INTO workflows (id, name, description, draft_source) VALUES (?, ?, ?, ?)",
                        (draft.id, draft.name, draft.description, draft.draft_source),
                    )
                else:
                    cursor = connection.execute(
                        "UPDATE workflows SET name = ?, description = ?, draft_source = ?, "
                        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (draft.name, draft.description, draft.draft_source, draft.id),
                    )
                    if cursor.rowcount == 0:
                        raise KeyError(draft.id)
                connection.execute(
                    "DELETE FROM workflow_draft_dependencies WHERE workflow_id = ?", (draft.id,)
                )
                connection.executemany(
                    "INSERT INTO workflow_draft_dependencies "
                    "(workflow_id, dependency_key, target_workflow_id) VALUES (?, ?, ?)",
                    [(draft.id, item.key, item.target_workflow_id) for item in draft.dependencies],
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        saved = self.get(draft.id)
        assert saved is not None
        return saved

    def delete(self, workflow_id: str) -> bool:
        with closing(self._connect()) as connection:
            cursor = connection.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
            connection.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _dependencies(connection: sqlite3.Connection, workflow_id: str) -> tuple[WorkflowDraftDependency, ...]:
        rows = connection.execute(
            "SELECT dependency_key, target_workflow_id FROM workflow_draft_dependencies "
            "WHERE workflow_id = ? ORDER BY dependency_key", (workflow_id,)
        ).fetchall()
        return tuple(WorkflowDraftDependency(row[0], row[1]) for row in rows)

    @staticmethod
    def _all_dependencies(connection: sqlite3.Connection) -> dict[str, tuple[WorkflowDraftDependency, ...]]:
        result: dict[str, list[WorkflowDraftDependency]] = {}
        rows = connection.execute(
            "SELECT workflow_id, dependency_key, target_workflow_id "
            "FROM workflow_draft_dependencies ORDER BY dependency_key"
        ).fetchall()
        for row in rows:
            result.setdefault(row[0], []).append(WorkflowDraftDependency(row[1], row[2]))
        return {key: tuple(value) for key, value in result.items()}

    @staticmethod
    def _from_row(row: sqlite3.Row, dependencies: tuple[WorkflowDraftDependency, ...]) -> WorkflowDraft:
        return WorkflowDraft(
            id=row["id"], name=row["name"], description=row["description"],
            draft_source=row["draft_source"], dependencies=dependencies,
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
