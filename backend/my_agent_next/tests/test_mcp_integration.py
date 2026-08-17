"""MCP persistence and real L6 stdio integration tests."""

import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

from my_agent_next.app.agent_profile import AgentProfile
from my_agent_next.app.agent_profile_repository import AgentProfileRepository
from my_agent_next.app.mcp_repository import McpServerRepository
from my_agent_next.app.mcp_service import McpService, invoke_mcp_tool
from my_agent_next.app.workflows.worker import EventEmitter, WorkerGateway, WorkerSpec
from my_agent_next.app.workflows.visual import compile_visual_graph


class _Queue:
    def __init__(self):
        self.items = []

    def put(self, item):
        self.items.append(item)


class _CancelEvent:
    @staticmethod
    def is_set():
        return False


class _ElementParentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.parents = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.parents[element_id] = tuple(self.stack)
        if tag not in {"input", "br", "meta", "link", "img", "hr"}:
            self.stack.append(element_id)

    def handle_endtag(self, tag):
        if self.stack:
            self.stack.pop()


class McpIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "app.db"
        agents = AgentProfileRepository(self.db_path)
        agents.save(AgentProfile(id="mabel", name="Mabel"))
        agents.save(AgentProfile(id="analysis", name="Norden"))
        self.repository = McpServerRepository(self.db_path)
        self.service = McpService(self.repository)
        self.service.save({
            "id": "l6_time",
            "name": "L6 Time Server",
            "transport": "stdio",
            "command": "python",
            "args": ["lecture/L6/mcp_server.py"],
            "cwd": ".",
            "env_names": [],
            "agent_ids": ["mabel"],
            "enabled": True,
        })

    def tearDown(self):
        self.temp.cleanup()

    def test_repository_persists_agent_bindings(self):
        server = self.repository.get("l6_time")
        self.assertEqual(server["agent_ids"], ["mabel"])
        self.assertEqual(self.repository.list_for_agent("analysis"), [])

    async def test_inspector_discovers_all_l6_capability_types(self):
        report = await self.service.inspect("l6_time")
        self.assertEqual(report["server_info"]["serverInfo"]["name"], "lesson-tools")
        self.assertEqual([item["name"] for item in report["tools"]], ["get_current_time"])
        self.assertEqual([item["name"] for item in report["resources"]], ["l6_overview"])
        self.assertEqual([item["name"] for item in report["prompts"]], ["python_teacher"])

    async def test_bound_agent_gets_prefixed_tool_and_can_call_it(self):
        tools = await self.service.tools_for_agent("mabel")
        self.assertIn("l6_time_get_current_time", tools)
        self.assertEqual(await self.service.tools_for_agent("analysis"), {})
        output = await invoke_mcp_tool(tools["l6_time_get_current_time"], {})
        self.assertIn("+08:00", output)
        self.assertNotIn("'type': 'text'", output)

    async def test_direct_workflow_mcp_gateway_calls_l6_server(self):
        queue = _Queue()
        gateway = WorkerGateway(
            WorkerSpec(
                run_id="run", workflow_id="flow", artifact_paths={},
                dependencies={}, inputs={"message": "time"},
                permission_mode="auto", recursion_limit=20,
            ),
            EventEmitter(queue, "run"), _CancelEvent(),
            run_id="run", workflow_id="flow", parent_run_id=None,
            call_depth=0, call_stack=("flow",),
        )
        import my_agent_next.app.mcp_service as service_module
        original = service_module.McpService
        service_module.McpService = lambda: self.service
        try:
            result = await gateway.call_mcp("l6_time", "get_current_time", {})
        finally:
            service_module.McpService = original
        self.assertIn("+08:00", str(result["result"]))
        self.assertEqual([item["event"] for item in queue.items], ["mcp_started", "mcp_output"])


class McpUiContractTests(unittest.TestCase):
    def test_mcp_navigation_and_visual_node_are_present(self):
        source = (
            Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
        ).read_text(encoding="utf-8")
        self.assertLess(
            source.index("switchTab('marketplace')\">🛒 Skill 市场"),
            source.index("switchTab('mcp')\">MCP 服务"),
        )
        self.assertIn("id=\"tab-mcp\"", source)
        self.assertIn("addVisualNode('mcp')", source)
        self.assertIn("mcp_started:\"MCP 输入\"", source)

    def test_mcp_modal_is_not_nested_in_workflow_help(self):
        source = (
            Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
        ).read_text(encoding="utf-8")
        parser = _ElementParentParser()
        parser.feed(source)
        self.assertNotIn("modalWorkflowHelp", parser.parents["tab-mcp"])
        self.assertNotIn("modalWorkflowHelp", parser.parents["modalMcp"])

    def test_visual_mcp_node_compiles_to_public_workflow_sdk(self):
        graph = {
            "version": 1,
            "nodes": [
                {"id": "start", "type": "start", "label": "Start", "config": {}},
                {"id": "mcp_time", "type": "mcp", "label": "Time", "config": {
                    "server_id": "l6_time", "tool_name": "get_current_time",
                    "arguments": {}, "output": "time_result",
                }},
                {"id": "answer", "type": "agent", "label": "Answer", "config": {
                    "agent_id": "analysis", "message": "Time: {time_result}", "output": "answer",
                }},
                {"id": "finish", "type": "end", "label": "End", "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "mcp_time"},
                {"id": "e2", "source": "mcp_time", "target": "answer"},
                {"id": "e3", "source": "answer", "target": "finish"},
            ],
        }
        _, source = compile_visual_graph(graph)
        self.assertIn(
            "flow.mcp('mcp_time', server='l6_time', tool='get_current_time'",
            source,
        )


if __name__ == "__main__":
    unittest.main()
