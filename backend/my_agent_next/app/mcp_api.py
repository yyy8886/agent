"""HTTP endpoints for MCP configuration and Inspector-style testing."""

from fastapi import APIRouter, HTTPException

from .mcp_service import McpService


router = APIRouter(prefix="/api/mcp", tags=["mcp"])
service = McpService()


@router.get("/servers")
def list_servers():
    service.ensure_l6_example()
    return service.list()


@router.post("/servers")
def save_server(payload: dict):
    try:
        return service.save(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/servers/{server_id}")
def delete_server(server_id: str):
    if not service.delete(server_id):
        raise HTTPException(404, "MCP server not found.")
    return {"deleted": True}


@router.post("/servers/{server_id}/inspect")
async def inspect_server(server_id: str):
    try:
        return await service.inspect(server_id)
    except Exception as exc:
        raise HTTPException(400, f"MCP inspection failed: {exc}") from exc


@router.post("/servers/{server_id}/tools/{tool_name}/call")
async def call_tool(server_id: str, tool_name: str, payload: dict):
    try:
        return await service.call_tool(server_id, tool_name, payload.get("arguments", {}))
    except Exception as exc:
        raise HTTPException(400, f"MCP tool call failed: {exc}") from exc


@router.post("/servers/{server_id}/resources/read")
async def read_resource(server_id: str, payload: dict):
    try:
        return await service.read_resource(server_id, str(payload.get("uri", "")))
    except Exception as exc:
        raise HTTPException(400, f"MCP resource read failed: {exc}") from exc


@router.post("/servers/{server_id}/prompts/{prompt_name}/get")
async def get_prompt(server_id: str, prompt_name: str, payload: dict):
    try:
        return await service.get_prompt(server_id, prompt_name, payload.get("arguments", {}))
    except Exception as exc:
        raise HTTPException(400, f"MCP prompt request failed: {exc}") from exc
