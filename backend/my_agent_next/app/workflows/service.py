"""Application rules for workflow draft editing."""

from __future__ import annotations

import re
import sqlite3

from .contract import WORKFLOW_IDENTIFIER_PATTERN
from .model import WorkflowDraft, WorkflowDraftDependency
from .repository import WorkflowRepository
from .source_validation import DEFAULT_SOURCE_POLICY, validate_workflow_source


DEFAULT_WORKFLOW_SOURCE = '''from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict, total=False):
    message: str
    answer: str


def process(state: State) -> dict:
    return {"answer": state.get("message", "")}


def build_workflow():
    graph = StateGraph(State)
    graph.add_node("process", process)
    graph.add_edge(START, "process")
    graph.add_edge("process", END)
    return graph.compile()
'''


class WorkflowConflictError(ValueError):
    pass


class WorkflowNotFoundError(ValueError):
    pass


class WorkflowService:
    def __init__(self, repository: WorkflowRepository | None = None) -> None:
        self.repository = repository or WorkflowRepository()

    def list(self) -> list[dict]:
        return [self._serialize(item) for item in self.repository.list()]

    def get(self, workflow_id: str) -> dict:
        item = self.repository.get(workflow_id)
        if item is None:
            raise WorkflowNotFoundError("工作流不存在。")
        return self._serialize(item)

    def validate(self, source: object) -> dict:
        if not isinstance(source, str):
            raise ValueError("draft_source 必须是字符串。")
        if len(source.encode("utf-8", errors="surrogatepass")) > DEFAULT_SOURCE_POLICY.max_source_bytes:
            raise ValueError(f"工作流代码不能超过 {DEFAULT_SOURCE_POLICY.max_source_bytes} 字节。")
        result = validate_workflow_source(source)
        return {
            "valid": result.valid,
            "issues": [
                {"code": issue.code, "message": issue.message, "line": issue.line, "column": issue.column}
                for issue in result.issues
            ],
            "imports": list(result.imports),
        }

    def create(self, payload: dict) -> dict:
        draft = self._parse(payload)
        if self.repository.get(draft.id) is not None:
            raise WorkflowConflictError("工作流 ID 已存在。")
        try:
            saved = self.repository.save(draft, create=True)
        except sqlite3.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        return self._serialize(saved)

    def update(self, workflow_id: str, payload: dict) -> dict:
        if self.repository.get(workflow_id) is None:
            raise WorkflowNotFoundError("工作流不存在。")
        draft = self._parse({**payload, "id": workflow_id})
        try:
            saved = self.repository.save(draft, create=False)
        except sqlite3.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        return self._serialize(saved)

    def delete(self, workflow_id: str) -> None:
        try:
            deleted = self.repository.delete(workflow_id)
        except sqlite3.IntegrityError as exc:
            raise WorkflowConflictError("该工作流仍被其他草稿依赖，不能删除。") from exc
        if not deleted:
            raise WorkflowNotFoundError("工作流不存在。")

    def _parse(self, payload: dict) -> WorkflowDraft:
        if not isinstance(payload, dict):
            raise ValueError("请求内容必须是对象。")
        workflow_id = str(payload.get("id", "")).strip()
        name = str(payload.get("name", "")).strip()
        description = str(payload.get("description", "")).strip()
        source = payload.get("draft_source", "")
        if not WORKFLOW_IDENTIFIER_PATTERN.fullmatch(workflow_id):
            raise ValueError("工作流 ID 必须以小写字母开头，只能包含小写字母、数字、下划线或连字符，长度为 2-64。")
        if not name or len(name) > 100:
            raise ValueError("工作流名称长度必须为 1-100。")
        if len(description) > 1000:
            raise ValueError("工作流说明不能超过 1000 个字符。")
        if not isinstance(source, str):
            raise ValueError("draft_source 必须是字符串。")
        if len(source.encode("utf-8", errors="surrogatepass")) > DEFAULT_SOURCE_POLICY.max_source_bytes:
            raise ValueError(f"工作流代码不能超过 {DEFAULT_SOURCE_POLICY.max_source_bytes} 字节。")
        raw_dependencies = payload.get("dependencies", [])
        if not isinstance(raw_dependencies, list):
            raise ValueError("dependencies 必须是数组。")
        dependencies: list[WorkflowDraftDependency] = []
        seen: set[str] = set()
        for raw in raw_dependencies:
            if not isinstance(raw, dict):
                raise ValueError("依赖项必须是对象。")
            key = str(raw.get("key", "")).strip()
            target = str(raw.get("target_workflow_id", "")).strip()
            if not WORKFLOW_IDENTIFIER_PATTERN.fullmatch(key):
                raise ValueError("依赖键格式不正确。")
            if key in seen:
                raise ValueError(f"依赖键重复：{key}")
            if target == workflow_id:
                raise ValueError("工作流不能依赖自身。")
            if self.repository.get(target) is None:
                raise ValueError(f"依赖的工作流不存在：{target}")
            seen.add(key)
            dependencies.append(WorkflowDraftDependency(key, target))
        return WorkflowDraft(workflow_id, name, description, source, tuple(dependencies))

    def _serialize(self, draft: WorkflowDraft) -> dict:
        return {
            "id": draft.id, "name": draft.name, "description": draft.description,
            "draft_source": draft.draft_source,
            "dependencies": [{"key": item.key, "target_workflow_id": item.target_workflow_id} for item in draft.dependencies],
            "created_at": draft.created_at, "updated_at": draft.updated_at,
            "validation": self.validate(draft.draft_source),
        }

    @staticmethod
    def _integrity_error(exc: sqlite3.IntegrityError) -> ValueError:
        if "UNIQUE" in str(exc):
            return WorkflowConflictError("工作流 ID 或依赖键已存在。")
        return ValueError("工作流依赖关系无效。")
