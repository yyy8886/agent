"""Data models for editable workflow drafts."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class WorkflowDraftDependency:
    key: str
    target_workflow_id: str


@dataclass(frozen=True, slots=True)
class WorkflowDraft:
    id: str
    name: str
    description: str
    draft_source: str
    dependencies: tuple[WorkflowDraftDependency, ...] = field(default_factory=tuple)
    editor_mode: str = "code"
    visual_graph: str = ""
    created_at: str | None = None
    updated_at: str | None = None
