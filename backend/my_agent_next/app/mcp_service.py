"""MCP configuration, discovery, inspection, and invocation service."""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from .agent_profile_repository import AgentProfileRepository
from .mcp_repository import McpServerRepository


MCP_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class McpService:
    def __init__(self, repository: McpServerRepository | None = None):
        self.repository = repository or McpServerRepository()

    def list(self) -> list[dict]:
        return self.repository.list()

    def save(self, payload: dict) -> dict:
        server_id = str(payload.get("id", "")).strip()
        name = str(payload.get("name", "")).strip()
        transport = str(payload.get("transport", "stdio")).strip()
        command = str(payload.get("command", "")).strip()
        if not MCP_ID.fullmatch(server_id):
            raise ValueError("MCP ID must start with a lowercase letter and contain only lowercase letters, digits, and underscores.")
        if not name:
            raise ValueError("MCP server name cannot be empty.")
        if transport != "stdio":
            raise ValueError("The first release supports stdio MCP servers only.")
        if not command:
            raise ValueError("MCP stdio command cannot be empty.")
        args = payload.get("args", [])
        env_names = payload.get("env_names", [])
        agent_ids = payload.get("agent_ids", [])
        if not all(isinstance(item, str) for item in args):
            raise ValueError("MCP args must be a string array.")
        if not all(isinstance(item, str) and item.strip() for item in env_names):
            raise ValueError("MCP environment variable names must be non-empty strings.")
        known_agents = {item.id for item in AgentProfileRepository(self.repository.db_path).list()}
        normalized_agents = list(dict.fromkeys(str(item).strip() for item in agent_ids if str(item).strip()))
        unknown = sorted(set(normalized_agents) - known_agents)
        if unknown:
            raise ValueError("Unknown Agent bindings: " + ", ".join(unknown))
        value = {
            "id": server_id, "name": name, "transport": transport,
            "command": command, "args": list(args), "cwd": str(payload.get("cwd", "")).strip(),
            "env_names": list(dict.fromkeys(env_names)), "agent_ids": normalized_agents,
            "enabled": bool(payload.get("enabled", True)),
        }
        return self.repository.save(value)

    def delete(self, server_id: str) -> bool:
        return self.repository.delete(server_id)

    def ensure_l6_example(self) -> dict | None:
        path = BACKEND_ROOT / "lecture" / "L6" / "mcp_server.py"
        if not path.is_file():
            return None
        current = self.repository.get("l6_time")
        if current:
            return current
        return self.repository.save({
            "id": "l6_time", "name": "L6 Time Server", "transport": "stdio",
            "command": "python", "args": ["lecture/L6/mcp_server.py"], "cwd": ".",
            "env_names": [], "agent_ids": [], "enabled": True,
        })

    async def inspect(self, server_id: str) -> dict:
        server = self._require(server_id)
        client = self._client([server])
        started = time.perf_counter()
        info = (await client.get_server_info(server_name=server_id))[server_id]
        async with client.session(server_id) as session:
            tools = (await session.list_tools()).tools
            resources = (await session.list_resources()).resources
            prompts = (await session.list_prompts()).prompts
        return {
            "server_id": server_id,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "server_info": _plain(info),
            "tools": [_plain(item) for item in tools],
            "resources": [_plain(item) for item in resources],
            "prompts": [_plain(item) for item in prompts],
        }

    async def call_tool(self, server_id: str, tool_name: str, arguments: dict) -> dict:
        server = self._require(server_id)
        started = time.perf_counter()
        async with self._client([server]).session(server_id) as session:
            result = await session.call_tool(tool_name, arguments or {})
        plain_result = _plain(result)
        return {
            "server_id": server_id, "tool": tool_name,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "text": mcp_protocol_result_text(plain_result),
            "result": plain_result,
        }

    async def read_resource(self, server_id: str, uri: str) -> dict:
        server = self._require(server_id)
        async with self._client([server]).session(server_id) as session:
            return _plain(await session.read_resource(uri))

    async def get_prompt(self, server_id: str, name: str, arguments: dict) -> dict:
        server = self._require(server_id)
        async with self._client([server]).session(server_id) as session:
            return _plain(await session.get_prompt(name, arguments=arguments or {}))

    async def tools_for_agent(self, agent_id: str) -> dict[str, Any]:
        servers = self.repository.list_for_agent(agent_id)
        if not servers:
            return {}
        tools = await self._client(servers, prefix=True).get_tools()
        return {tool.name: tool for tool in tools}

    async def call_bound_tool(self, agent_id: str, name: str, arguments: dict) -> str:
        tool = (await self.tools_for_agent(agent_id)).get(name)
        if tool is None:
            return f"MCP tool is unavailable or not authorized: {name}"
        return await invoke_mcp_tool(tool, arguments)

    def _require(self, server_id: str) -> dict:
        server = self.repository.get(server_id)
        if not server or not server["enabled"]:
            raise ValueError(f"MCP server is missing or disabled: {server_id}")
        return server

    def _client(self, servers: list[dict], prefix: bool = False) -> MultiServerMCPClient:
        return MultiServerMCPClient(
            {item["id"]: self._connection(item) for item in servers},
            tool_name_prefix=prefix,
        )

    @staticmethod
    def _connection(server: dict) -> dict:
        command = sys.executable if server["command"] in {"python", "python3"} else server["command"]
        cwd = _resolve_portable_path(server.get("cwd") or ".")
        args = [
            str(_resolve_portable_path(item)) if _looks_like_relative_file(item) else item
            for item in server["args"]
        ]
        env = {name: os.environ[name] for name in server["env_names"] if name in os.environ}
        return {
            "transport": "stdio", "command": command, "args": args,
            "cwd": str(cwd), "env": env,
        }


def _resolve_portable_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (_mcp_path_base() / path).resolve()


def _mcp_path_base() -> Path:
    """Resolve relative MCP paths without storing platform-specific locations."""
    configured = os.environ.get("MY_AGENT_MCP_ROOT") or os.environ.get("MY_AGENT_HOME")
    return Path(configured).expanduser().resolve() if configured else BACKEND_ROOT


def _looks_like_relative_file(value: str) -> bool:
    return not Path(value).is_absolute() and ("/" in value or "\\" in value)


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


async def invoke_mcp_tool(tool: Any, arguments: dict) -> str:
    """Convert adapter content blocks into a stable ToolMessage string."""
    return mcp_tool_result_text(await tool.ainvoke(arguments or {}))


def mcp_tool_result_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        text_parts = [
            str(item.get("text", ""))
            for item in value
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        if text_parts:
            return "\n".join(part for part in text_parts if part)
    plain = _plain(value)
    import json
    return json.dumps(plain, ensure_ascii=False, default=str)


def mcp_protocol_result_text(value: Any) -> str:
    content = value.get("content", []) if isinstance(value, dict) else []
    return mcp_tool_result_text(content)
