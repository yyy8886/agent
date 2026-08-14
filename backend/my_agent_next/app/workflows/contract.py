"""Stable interface between user-authored graphs and the application runtime."""

from __future__ import annotations

import math
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator, Protocol, TypeAlias


WORKFLOW_CONTRACT_VERSION = 1
WORKFLOW_ENTRYPOINT = "build_workflow"
MAX_PAYLOAD_DEPTH = 32
WORKFLOW_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
WorkflowPayload: TypeAlias = dict[str, JsonValue]

# Keep this list independent from internal workflow modules. The source validator
# uses it to enforce the symbols available from my_agent_next.workflow_sdk.
PUBLIC_WORKFLOW_SDK_SYMBOLS = frozenset(
    {
        "JsonValue",
        "WORKFLOW_CONTRACT_VERSION",
        "WORKFLOW_ENTRYPOINT",
        "WorkflowCancelledError",
        "WorkflowContractError",
        "WorkflowPayload",
        "WorkflowRunInfo",
        "WorkflowRuntime",
        "normalize_workflow_payload",
    }
)


class WorkflowContractError(ValueError):
    """A workflow violated the public input, output, or runtime contract."""


class WorkflowCancelledError(RuntimeError):
    """Raised cooperatively when the current workflow run is cancelled."""


@dataclass(frozen=True, slots=True)
class WorkflowDependency:
    """One immutable child-workflow dependency captured on publication."""

    key: str
    workflow_id: str
    workflow_version: int

    def __post_init__(self) -> None:
        _validate_identifier(self.key, "dependency key")
        _validate_identifier(self.workflow_id, "workflow_id")
        if (
            not isinstance(self.workflow_version, int)
            or isinstance(self.workflow_version, bool)
            or self.workflow_version < 1
        ):
            raise WorkflowContractError("workflow_version 必须大于等于 1。")


@dataclass(frozen=True, slots=True)
class WorkflowRunInfo:
    """Read-only identity and call-chain metadata for one workflow run."""

    run_id: str
    root_run_id: str
    workflow_id: str
    workflow_version: int | None = None
    parent_run_id: str | None = None
    parent_node_id: str | None = None
    call_depth: int = 0
    permission_mode: str = "manual"

    def __post_init__(self) -> None:
        for field_name in ("run_id", "root_run_id", "workflow_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise WorkflowContractError(f"{field_name} 不能为空。")
        for field_name in ("parent_run_id", "parent_node_id"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise WorkflowContractError(f"{field_name} 必须是非空字符串或 None。")
        if self.workflow_version is not None and (
            not isinstance(self.workflow_version, int)
            or isinstance(self.workflow_version, bool)
            or self.workflow_version < 1
        ):
            raise WorkflowContractError("workflow_version 必须大于等于 1。")
        if (
            not isinstance(self.call_depth, int)
            or isinstance(self.call_depth, bool)
            or self.call_depth < 0
        ):
            raise WorkflowContractError("call_depth 不能小于 0。")
        if (
            not isinstance(self.permission_mode, str)
            or self.permission_mode not in {"manual", "plan", "auto"}
        ):
            raise WorkflowContractError("permission_mode 必须是 manual、plan 或 auto。")

        has_parent_run = self.parent_run_id is not None
        has_parent_node = self.parent_node_id is not None
        if has_parent_run != has_parent_node:
            raise WorkflowContractError(
                "parent_run_id 和 parent_node_id 必须同时提供或同时为空。"
            )
        if self.call_depth == 0:
            if has_parent_run or self.root_run_id != self.run_id:
                raise WorkflowContractError(
                    "根运行不能包含父运行，且 root_run_id 必须等于 run_id。"
                )
        elif not has_parent_run:
            raise WorkflowContractError("子运行必须包含父运行和父节点。")


class _WorkflowGateway(Protocol):
    """Worker-owned capability implementation hidden from workflow source."""

    async def call_agent(
        self,
        agent_id: str,
        inputs: WorkflowPayload,
        *,
        timeout_seconds: float | None = None,
    ) -> WorkflowPayload: ...

    async def call_tool(
        self,
        tool_name: str,
        arguments: WorkflowPayload,
        *,
        timeout_seconds: float | None = None,
    ) -> WorkflowPayload: ...

    async def call_workflow(
        self,
        dependency_key: str,
        inputs: WorkflowPayload,
        *,
        timeout_seconds: float | None = None,
    ) -> WorkflowPayload: ...

    async def emit_event(self, event_type: str, data: WorkflowPayload) -> None: ...

    def raise_if_cancelled(self) -> None: ...


_current_gateway: ContextVar[_WorkflowGateway | None] = ContextVar(
    "workflow_gateway",
    default=None,
)


@dataclass(frozen=True, slots=True)
class WorkflowRuntime:
    """LangGraph-compatible context injected into every workflow node.

    Only serializable run metadata appears in LangGraph's context schema. The
    worker capability gateway is bound separately for the duration of a run.
    """

    run_info: WorkflowRunInfo
    dependency_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.dependency_keys, tuple):
            raise WorkflowContractError("dependency_keys 必须是字符串元组。")
        seen: set[str] = set()
        for key in self.dependency_keys:
            _validate_identifier(key, "dependency key")
            if key in seen:
                raise WorkflowContractError(f"重复的 dependency key：{key}")
            seen.add(key)

    async def call_agent(
        self,
        agent_id: str,
        inputs: WorkflowPayload,
        *,
        timeout_seconds: float | None = None,
    ) -> WorkflowPayload:
        _validate_identifier(agent_id, "agent_id")
        _validate_timeout(timeout_seconds)
        result = await _get_gateway().call_agent(
            agent_id,
            normalize_workflow_payload(inputs, label="agent inputs"),
            timeout_seconds=timeout_seconds,
        )
        return normalize_workflow_payload(result, label="agent output")

    async def call_tool(
        self,
        tool_name: str,
        arguments: WorkflowPayload,
        *,
        timeout_seconds: float | None = None,
    ) -> WorkflowPayload:
        _validate_identifier(tool_name, "tool_name")
        _validate_timeout(timeout_seconds)
        result = await _get_gateway().call_tool(
            tool_name,
            normalize_workflow_payload(arguments, label="tool arguments"),
            timeout_seconds=timeout_seconds,
        )
        return normalize_workflow_payload(result, label="tool output")

    async def call_workflow(
        self,
        dependency_key: str,
        inputs: WorkflowPayload,
        *,
        timeout_seconds: float | None = None,
    ) -> WorkflowPayload:
        _validate_identifier(dependency_key, "dependency key")
        if dependency_key not in self.dependency_keys:
            raise WorkflowContractError(
                f"未声明或未冻结的子工作流依赖：{dependency_key}"
            )
        _validate_timeout(timeout_seconds)
        result = await _get_gateway().call_workflow(
            dependency_key,
            normalize_workflow_payload(inputs, label="workflow inputs"),
            timeout_seconds=timeout_seconds,
        )
        return normalize_workflow_payload(result, label="workflow output")

    async def emit_event(self, event_type: str, data: WorkflowPayload) -> None:
        if not isinstance(event_type, str) or not event_type.strip():
            raise WorkflowContractError("event_type 不能为空。")
        await _get_gateway().emit_event(
            event_type.strip(),
            normalize_workflow_payload(data, label="event data"),
        )

    def raise_if_cancelled(self) -> None:
        _get_gateway().raise_if_cancelled()


@contextmanager
def _bind_workflow_gateway(gateway: _WorkflowGateway) -> Iterator[None]:
    """Bind worker capabilities to the current async context during graph execution."""

    token = _current_gateway.set(gateway)
    try:
        yield
    finally:
        _current_gateway.reset(token)


def normalize_workflow_payload(value: object, *, label: str = "payload") -> WorkflowPayload:
    """Validate and copy a workflow input or output into plain JSON containers."""

    normalized = _normalize_json_value(value, path=label, depth=0)
    if not isinstance(normalized, dict):
        raise WorkflowContractError(f"{label} 顶层必须是 JSON 对象。")
    return normalized


def _normalize_json_value(value: object, *, path: str, depth: int) -> JsonValue:
    if depth > MAX_PAYLOAD_DEPTH:
        raise WorkflowContractError(f"{path} 超过最大嵌套深度 {MAX_PAYLOAD_DEPTH}。")
    if value is None or type(value) in (str, bool):
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise WorkflowContractError(f"{path} 不能包含 NaN 或 Infinity。")
        return value
    if type(value) is list:
        return [
            _normalize_json_value(item, path=f"{path}[{index}]", depth=depth + 1)
            for index, item in enumerate(value)
        ]
    if type(value) is dict:
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise WorkflowContractError(f"{path} 的对象键必须是字符串。")
            result[key] = _normalize_json_value(
                item,
                path=f"{path}.{key}",
                depth=depth + 1,
            )
        return result
    raise WorkflowContractError(
        f"{path} 包含不能序列化为 JSON 的类型：{type(value).__name__}。"
    )


def _get_gateway() -> _WorkflowGateway:
    gateway = _current_gateway.get()
    if gateway is None:
        raise WorkflowContractError("WorkflowRuntime 只能在工作流 Worker 运行期间使用。")
    return gateway


def _validate_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not WORKFLOW_IDENTIFIER_PATTERN.fullmatch(value):
        raise WorkflowContractError(
            f"{label} 必须以小写字母开头，且只能包含小写字母、数字、下划线和连字符。"
        )


def _validate_timeout(value: float | None) -> None:
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise WorkflowContractError("timeout_seconds 必须是大于 0 的有限数字或 None。")
