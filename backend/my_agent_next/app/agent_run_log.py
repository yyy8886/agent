"""Incremental diagnostic logs for Agent chat runs."""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path

from .runtime_paths import DATA_DIR


DEFAULT_LOG_ROOT = DATA_DIR / "agent-runs"
_SENSITIVE_KEY = re.compile(
    r"(api[_-]?key|authorization|password|secret|token|cookie)",
    re.IGNORECASE,
)


def redact_sensitive(value):
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_sensitive(item) for item in value]
    return value


class AgentRunLog:
    """Write one append-only JSONL file per run so incomplete runs remain inspectable."""

    def __init__(
        self,
        *,
        agent_id: str,
        thread_id: str,
        user_content: str,
        max_iterations: int,
        root: Path | None = None,
    ):
        now = datetime.now().astimezone()
        run_id = f"{now:%H%M%S}-{uuid.uuid4().hex[:8]}"
        directory = (root or DEFAULT_LOG_ROOT) / f"{now:%Y-%m-%d}"
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{run_id}.jsonl"
        self.run_id = run_id
        self._lock = threading.Lock()
        self._output_buffer = ""
        self._output_characters = 0
        self.write("run_started", {
            "agent_id": agent_id,
            "thread_id": thread_id,
            "user_content": user_content,
            "max_agent_iterations": max_iterations,
        })

    def write(self, event: str, data: dict | None = None) -> None:
        record = {
            "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "run_id": self.run_id,
            "event": event,
            "data": redact_sensitive(data or {}),
        }
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(line + "\n")

    def append_output(self, text: str) -> None:
        if not text:
            return
        self._output_buffer += text
        self._output_characters += len(text)
        if len(self._output_buffer) >= 2048:
            self.flush_output()

    def flush_output(self) -> None:
        if not self._output_buffer:
            return
        text, self._output_buffer = self._output_buffer, ""
        self.write("model_output", {"text": text})

    def finish(self, status: str, **data) -> None:
        self.flush_output()
        self.write(status, {
            "output_characters": self._output_characters,
            **data,
        })
