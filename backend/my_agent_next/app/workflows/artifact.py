"""Materialize validated workflow source as immutable Python artifacts."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .model import WorkflowDraft
from .source_validation import validate_workflow_source


DEFAULT_ARTIFACT_DIR = Path(__file__).resolve().parents[4] / ".workflow_artifacts"


@dataclass(frozen=True, slots=True)
class WorkflowArtifact:
    workflow_id: str
    sha256: str
    path: Path


class WorkflowArtifactStore:
    def __init__(self, root: str | Path = DEFAULT_ARTIFACT_DIR) -> None:
        self.root = Path(root)

    def materialize(self, draft: WorkflowDraft) -> WorkflowArtifact:
        validation = validate_workflow_source(draft.draft_source)
        if not validation.valid:
            codes = ", ".join(issue.code for issue in validation.issues)
            raise ValueError(f"工作流静态验证未通过：{codes}")
        digest = hashlib.sha256(draft.draft_source.encode("utf-8")).hexdigest()
        directory = self.root / draft.id
        path = directory / f"{digest}.py"
        if path.exists():
            return WorkflowArtifact(draft.id, digest, path)
        directory.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{digest}.", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(draft.draft_source)
            os.replace(temp_name, path)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise
        return WorkflowArtifact(draft.id, digest, path)
