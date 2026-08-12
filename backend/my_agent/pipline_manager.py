"""Persistence and validation for editable Agent pipelines."""

from __future__ import annotations

import json
import re
from pathlib import Path

from my_agent.pipline import PipelineDefinition


DATA_FILE = Path(__file__).resolve().parent / "data" / "pipelines.json"
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")


class PipelineManager:
    def _load(self) -> dict:
        if not DATA_FILE.exists():
            return {"pipelines": {}}
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list(self) -> list[dict]:
        return list(self._load().get("pipelines", {}).values())

    def save(self, payload: dict, known_agents: set[str]) -> dict:
        pipeline = PipelineDefinition.from_dict(payload)
        if not ID_PATTERN.fullmatch(pipeline.id):
            raise ValueError("工作流 ID 只能使用小写字母、数字、下划线和连字符。")
        if pipeline.entry_agent not in known_agents:
            raise ValueError("入口 Agent 不存在。")
        for edge in pipeline.edges:
            if edge.source not in known_agents or edge.target not in known_agents:
                raise ValueError(f"交接边包含不存在的 Agent：{edge.source} -> {edge.target}")
            if edge.source == edge.target:
                raise ValueError("第一版控制台不允许 Agent 直接交接给自己。")
        data = self._load()
        stored = pipeline.to_dict()
        data.setdefault("pipelines", {})[pipeline.id] = stored
        self._save(data)
        return stored

    def delete(self, pipeline_id: str) -> bool:
        data = self._load()
        removed = data.setdefault("pipelines", {}).pop(pipeline_id, None)
        self._save(data)
        return removed is not None
