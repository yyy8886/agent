"""Small executable builder layered on top of native LangGraph."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from .contract import WorkflowContractError, WorkflowRuntime


State = dict[str, Any]
Node = Callable[[State], Mapping[str, Any] | Awaitable[Mapping[str, Any]]]
Condition = Callable[[State], str | bool]
_FIELD_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class Workflow:
    """Build a directly executable LangGraph without repetitive boilerplate."""

    def __init__(self) -> None:
        self._graph = StateGraph(dict, context_schema=WorkflowRuntime)
        self._nodes: set[str] = set()

    def node(self, name: str, function: Node) -> "Workflow":
        self._add_node(name, function)
        return self

    def agent(
        self,
        name: str,
        *,
        agent: str,
        message: str,
        output: str = "answer",
        timeout_seconds: float | None = None,
    ) -> "Workflow":
        async def call(state: State, runtime: Runtime[WorkflowRuntime]) -> dict:
            result = await runtime.context.call_agent(
                agent,
                {"message": _render(message, state)},
                timeout_seconds=timeout_seconds,
            )
            return {**state, output: str(result.get("answer", ""))}

        self._add_node(name, call)
        return self

    def tool(
        self,
        name: str,
        *,
        tool: str,
        arguments: Mapping[str, Any],
        output: str,
        timeout_seconds: float | None = None,
    ) -> "Workflow":
        async def call(state: State, runtime: Runtime[WorkflowRuntime]) -> dict:
            result = await runtime.context.call_tool(
                tool,
                _render_mapping(arguments, state),
                timeout_seconds=timeout_seconds,
            )
            return {**state, output: result}

        self._add_node(name, call)
        return self

    def skill(
        self,
        name: str,
        *,
        skill: str,
        arguments: Mapping[str, Any],
        output: str,
        timeout_seconds: float | None = None,
    ) -> "Workflow":
        async def call(state: State, runtime: Runtime[WorkflowRuntime]) -> dict:
            result = await runtime.context.call_skill(
                skill,
                _render_mapping(arguments, state),
                timeout_seconds=timeout_seconds,
            )
            return {**state, output: result}

        self._add_node(name, call)
        return self

    def workflow(
        self,
        name: str,
        *,
        dependency: str,
        inputs: Mapping[str, Any],
        output: str,
        timeout_seconds: float | None = None,
    ) -> "Workflow":
        async def call(state: State, runtime: Runtime[WorkflowRuntime]) -> dict:
            result = await runtime.context.call_workflow(
                dependency,
                _render_mapping(inputs, state),
                timeout_seconds=timeout_seconds,
            )
            return {**state, output: result}

        self._add_node(name, call)
        return self

    def edge(self, source: str, target: str) -> "Workflow":
        self._graph.add_edge(_endpoint(source), _endpoint(target))
        return self

    def if_(
        self,
        source: str,
        condition: Condition,
        *,
        then: str,
        otherwise: str,
    ) -> "Workflow":
        def route(state: State) -> str:
            result = condition(state)
            if isinstance(result, bool):
                return "then" if result else "otherwise"
            if result not in {"then", "otherwise"}:
                raise WorkflowContractError(
                    "Workflow.if_ condition must return bool, 'then', or 'otherwise'."
                )
            return result

        self._graph.add_conditional_edges(
            _endpoint(source),
            route,
            {"then": _endpoint(then), "otherwise": _endpoint(otherwise)},
        )
        return self

    def while_(
        self,
        source: str,
        condition: Callable[[State], bool],
        *,
        body: str,
        done: str,
        max_iterations: int,
    ) -> "Workflow":
        if not isinstance(max_iterations, int) or isinstance(max_iterations, bool):
            raise WorkflowContractError("max_iterations must be an integer.")
        if not 1 <= max_iterations <= 100:
            raise WorkflowContractError("max_iterations must be between 1 and 100.")
        guard = f"__while_guard_{source}"
        counter = f"__while_count_{source}"

        def increment(state: State) -> dict:
            return {**state, counter: int(state.get(counter, 0)) + 1}

        def route(state: State) -> str:
            if int(state.get(counter, 0)) > max_iterations:
                return "done"
            return "body" if bool(condition(state)) else "done"

        self._add_node(guard, increment)
        self._graph.add_edge(source, guard)
        self._graph.add_conditional_edges(
            guard,
            route,
            {"body": body, "done": _endpoint(done)},
        )
        self._graph.add_edge(body, source)
        return self

    def compile(self):
        return self._graph.compile()

    def _add_node(self, name: str, function: Callable[..., Any]) -> None:
        if not isinstance(name, str) or not name.strip():
            raise WorkflowContractError("Node name cannot be empty.")
        if name in self._nodes:
            raise WorkflowContractError(f"Duplicate node: {name}")
        self._graph.add_node(name, function)
        self._nodes.add(name)


def _endpoint(value: str):
    if value == "START":
        return START
    if value == "END":
        return END
    return value


def _render(template: str, state: State) -> str:
    if not isinstance(template, str):
        raise WorkflowContractError("Message template must be a string.")

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in state:
            raise WorkflowContractError(f"Missing context field: {key}")
        return str(state[key])

    return _FIELD_PATTERN.sub(replace, template)


def _render_mapping(value: Mapping[str, Any], state: State) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkflowContractError("Arguments must be an object.")
    return {str(key): _render_value(item, state) for key, item in value.items()}


def _render_value(value: Any, state: State) -> Any:
    if isinstance(value, str):
        return _render(value, state)
    if isinstance(value, Mapping):
        return _render_mapping(value, state)
    if isinstance(value, list):
        return [_render_value(item, state) for item in value]
    return value
