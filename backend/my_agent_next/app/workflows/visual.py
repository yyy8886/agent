"""Validation and deterministic source generation for visual workflows."""

from __future__ import annotations

import json
import re
from collections import deque
from typing import Any

from .contract import WORKFLOW_IDENTIFIER_PATTERN


NODE_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
NODE_TYPES = {"start", "end", "agent", "skill", "tool", "mcp", "workflow", "condition"}
CONDITION_OPERATORS = {"equals", "not_equals", "contains", "truthy"}
MAX_NODES = 100
MAX_EDGES = 200


def empty_visual_graph() -> dict:
    return {
        "version": 1,
        "nodes": [
            {"id": "start", "type": "start", "label": "开始", "position": {"x": 80, "y": 180}},
            {"id": "finish", "type": "end", "label": "结束", "position": {"x": 560, "y": 180}},
        ],
        "edges": [],
    }


def compile_visual_graph(value: object) -> tuple[dict, str]:
    graph = _normalize_graph(value)
    nodes = {node["id"]: node for node in graph["nodes"]}
    outgoing: dict[str, list[dict]] = {node_id: [] for node_id in nodes}
    incoming: dict[str, list[dict]] = {node_id: [] for node_id in nodes}
    for edge in graph["edges"]:
        outgoing[edge["source"]].append(edge)
        incoming[edge["target"]].append(edge)

    starts = [node for node in nodes.values() if node["type"] == "start"]
    ends = [node for node in nodes.values() if node["type"] == "end"]
    if len(starts) != 1:
        raise ValueError("可视化工作流必须有且只有一个开始节点。")
    if not ends:
        raise ValueError("可视化工作流至少需要一个结束节点。")
    if not any(
        node["type"] == "agent" and node["config"].get("output") == "answer"
        for node in nodes.values()
    ):
        raise ValueError("可视化工作流至少需要一个输出到 answer 的 Agent 节点。")
    if incoming[starts[0]["id"]]:
        raise ValueError("开始节点不能有入线。")
    for node in ends:
        if outgoing[node["id"]]:
            raise ValueError("结束节点不能有出线。")

    _validate_connections(nodes, outgoing, incoming)
    _validate_reachability(starts[0]["id"], nodes, outgoing)
    source = _generate_source(graph, nodes, outgoing)
    return graph, source


def _normalize_graph(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("visual_graph 必须是对象。")
    raw_nodes = value.get("nodes")
    raw_edges = value.get("edges")
    if not isinstance(raw_nodes, list) or not 3 <= len(raw_nodes) <= MAX_NODES:
        raise ValueError(f"可视化节点数量必须在 3-{MAX_NODES} 之间。")
    if not isinstance(raw_edges, list) or len(raw_edges) > MAX_EDGES:
        raise ValueError(f"可视化连线不能超过 {MAX_EDGES} 条。")

    nodes: list[dict] = []
    ids: set[str] = set()
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            raise ValueError("节点必须是对象。")
        node_id = str(raw.get("id", "")).strip()
        node_type = str(raw.get("type", "")).strip()
        if not NODE_ID.fullmatch(node_id) or node_id in ids:
            raise ValueError(f"节点 ID 无效或重复：{node_id}")
        if node_type not in NODE_TYPES:
            raise ValueError(f"不支持的节点类型：{node_type}")
        ids.add(node_id)
        config = raw.get("config") or {}
        if not isinstance(config, dict):
            raise ValueError(f"节点 {node_id} 的配置必须是对象。")
        position = raw.get("position") or {}
        x = _coordinate(position.get("x", 0))
        y = _coordinate(position.get("y", 0))
        nodes.append({
            "id": node_id,
            "type": node_type,
            "label": str(raw.get("label") or node_id)[:100],
            "position": {"x": x, "y": y},
            "manual_position": bool(raw.get("manual_position", False)),
            "config": _normalize_config(node_id, node_type, config),
        })

    edges: list[dict] = []
    edge_pairs: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(raw_edges):
        if not isinstance(raw, dict):
            raise ValueError("连线必须是对象。")
        source = str(raw.get("source", "")).strip()
        target = str(raw.get("target", "")).strip()
        branch = str(raw.get("branch", "")).strip()
        if source not in ids or target not in ids:
            raise ValueError("连线引用了不存在的节点。")
        if source == target:
            raise ValueError("节点不能直接连接自身。")
        key = (source, target, branch)
        if key in edge_pairs:
            raise ValueError("存在重复连线。")
        edge_pairs.add(key)
        edges.append({"id": str(raw.get("id") or f"edge_{index}"), "source": source, "target": target, "branch": branch})
    return {"version": 1, "nodes": nodes, "edges": edges}


def _normalize_config(node_id: str, node_type: str, config: dict) -> dict:
    if node_type in {"start", "end"}:
        return {}
    if node_type == "agent":
        agent_id = str(config.get("agent_id", "")).strip()
        message = str(config.get("message", "")).strip()
        output = str(config.get("output", "answer")).strip()
        if not WORKFLOW_IDENTIFIER_PATTERN.fullmatch(agent_id):
            raise ValueError(f"Agent 节点 {node_id} 缺少有效 agent_id。")
        _validate_field(output, node_id)
        if not message:
            raise ValueError(f"Agent 节点 {node_id} 的任务不能为空。")
        return {"agent_id": agent_id, "message": message, "output": output}
    if node_type in {"skill", "tool"}:
        key = "skill_name" if node_type == "skill" else "tool_name"
        capability = str(config.get(key, "")).strip()
        output = str(config.get("output", f"{node_id}_result")).strip()
        arguments = config.get("arguments") or {}
        if not WORKFLOW_IDENTIFIER_PATTERN.fullmatch(capability):
            raise ValueError(f"节点 {node_id} 缺少有效 {key}。")
        if not isinstance(arguments, dict):
            raise ValueError(f"节点 {node_id} 的参数必须是对象。")
        _validate_field(output, node_id)
        return {key: capability, "arguments": arguments, "output": output}
    if node_type == "mcp":
        server_id = str(config.get("server_id", "")).strip()
        tool_name = str(config.get("tool_name", "")).strip()
        output = str(config.get("output", f"{node_id}_result")).strip()
        arguments = config.get("arguments") or {}
        if not WORKFLOW_IDENTIFIER_PATTERN.fullmatch(server_id):
            raise ValueError(f"MCP node {node_id} is missing a valid server_id.")
        if not WORKFLOW_IDENTIFIER_PATTERN.fullmatch(tool_name):
            raise ValueError(f"MCP node {node_id} is missing a valid tool_name.")
        if not isinstance(arguments, dict):
            raise ValueError(f"MCP node {node_id} arguments must be an object.")
        _validate_field(output, node_id)
        return {"server_id": server_id, "tool_name": tool_name, "arguments": arguments, "output": output}
    if node_type == "workflow":
        dependency = str(config.get("dependency", "")).strip()
        output = str(config.get("output", f"{node_id}_result")).strip()
        inputs = config.get("inputs") or {"message": "{message}"}
        if not WORKFLOW_IDENTIFIER_PATTERN.fullmatch(dependency):
            raise ValueError(f"子工作流节点 {node_id} 缺少有效依赖键。")
        if not isinstance(inputs, dict):
            raise ValueError(f"子工作流节点 {node_id} 的输入必须是对象。")
        _validate_field(output, node_id)
        return {"dependency": dependency, "inputs": inputs, "output": output}
    field = str(config.get("field", "")).strip()
    operator = str(config.get("operator", "truthy")).strip()
    if not FIELD_NAME.fullmatch(field) or operator not in CONDITION_OPERATORS:
        raise ValueError(f"条件节点 {node_id} 的字段或操作符无效。")
    return {"field": field, "operator": operator, "value": config.get("value")}


def _validate_connections(nodes: dict, outgoing: dict, incoming: dict) -> None:
    for node_id, node in nodes.items():
        if node["type"] != "start" and not incoming[node_id]:
            raise ValueError(f"节点 {node_id} 没有入线。")
        if node["type"] != "end" and not outgoing[node_id]:
            raise ValueError(f"节点 {node_id} 没有出线。")
        if node["type"] == "condition":
            if len(incoming[node_id]) != 1:
                raise ValueError(f"条件节点 {node_id} 必须有且只有一条入线。")
            branches = {edge["branch"] for edge in outgoing[node_id]}
            if len(outgoing[node_id]) != 2 or branches != {"then", "otherwise"}:
                raise ValueError(f"条件节点 {node_id} 必须各有一条“是”和“否”连线。")
        elif len(outgoing[node_id]) > 1:
            raise ValueError(f"节点 {node_id} 有多个出口，请先加入条件节点。")


def _validate_reachability(start: str, nodes: dict, outgoing: dict) -> None:
    visited: set[str] = set()
    queue = deque([start])
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        queue.extend(edge["target"] for edge in outgoing[current])
    missing = sorted(set(nodes) - visited)
    if missing:
        raise ValueError("存在从开始节点无法到达的节点：" + "、".join(missing))


def _generate_source(graph: dict, nodes: dict, outgoing: dict) -> str:
    lines = ["from my_agent_next.workflow_sdk import Workflow", ""]
    for node in graph["nodes"]:
        if node["type"] != "condition":
            continue
        config = node["config"]
        lines.extend([
            f"def _condition_{node['id']}(state):",
            f"    current = state.get({config['field']!r})",
        ])
        operator = config["operator"]
        if operator == "equals":
            lines.append(f"    return current == {config['value']!r}")
        elif operator == "not_equals":
            lines.append(f"    return current != {config['value']!r}")
        elif operator == "contains":
            lines.append(f"    return {config['value']!r} in current if current is not None else False")
        else:
            lines.append("    return bool(current)")
        lines.append("")
    lines.extend(["def build_workflow():", "    flow = Workflow()"])
    for node in graph["nodes"]:
        node_id = node["id"]
        node_type = node["type"]
        config = node["config"]
        if node_type == "agent":
            lines.append(
                f"    flow.agent({node_id!r}, agent={config['agent_id']!r}, "
                f"message={config['message']!r}, output={config['output']!r})"
            )
        elif node_type == "skill":
            lines.append(
                f"    flow.skill({node_id!r}, skill={config['skill_name']!r}, "
                f"arguments={config['arguments']!r}, output={config['output']!r})"
            )
        elif node_type == "tool":
            lines.append(
                f"    flow.tool({node_id!r}, tool={config['tool_name']!r}, "
                f"arguments={config['arguments']!r}, output={config['output']!r})"
            )
        elif node_type == "mcp":
            lines.append(
                f"    flow.mcp({node_id!r}, server={config['server_id']!r}, "
                f"tool={config['tool_name']!r}, arguments={config['arguments']!r}, "
                f"output={config['output']!r})"
            )
        elif node_type == "workflow":
            lines.append(
                f"    flow.workflow({node_id!r}, dependency={config['dependency']!r}, "
                f"inputs={config['inputs']!r}, output={config['output']!r})"
            )
    for node in graph["nodes"]:
        source = node["id"]
        node_type = node["type"]
        if node_type == "condition":
            branches = {edge["branch"]: edge["target"] for edge in outgoing[source]}
            predecessor = next(edge["source"] for edge in graph["edges"] if edge["target"] == source)
            lines.append(
                f"    flow.if_({predecessor!r}, _condition_{source}, "
                f"then={_code_endpoint(branches['then'], nodes)}, otherwise={_code_endpoint(branches['otherwise'], nodes)})"
            )
            continue
        for edge in outgoing[source]:
            if nodes[edge["target"]]["type"] == "condition":
                continue
            lines.append(
                f"    flow.edge({_code_endpoint(source, nodes)}, "
                f"{_code_endpoint(edge['target'], nodes)})"
            )
    lines.extend(["    return flow.compile()", ""])
    return "\n".join(lines)


def _code_endpoint(node_id: str, nodes: dict) -> str:
    node_type = nodes[node_id]["type"]
    return repr("START" if node_type == "start" else "END" if node_type == "end" else node_id)


def _validate_field(value: str, node_id: str) -> None:
    if not FIELD_NAME.fullmatch(value):
        raise ValueError(f"节点 {node_id} 的输出字段无效。")


def _coordinate(value: Any) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return 0
    return max(-5000, min(5000, number))


def visual_graph_json(graph: dict) -> str:
    return json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
