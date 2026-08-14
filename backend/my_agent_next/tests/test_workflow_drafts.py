"""Workflow draft CRUD tests use an isolated temporary SQLite database."""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from my_agent_next.app.workflows.api import create_workflow_router
from my_agent_next.app.workflows.repository import WorkflowRepository
from my_agent_next.app.workflows.service import WorkflowService


class WorkflowDraftTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        repository = WorkflowRepository(Path(self.temp_dir.name) / "workflows.db")
        self.service = WorkflowService(repository)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_saves_invalid_source_as_a_draft(self):
        result = self.service.create(
            {"id": "draft-flow", "name": "Draft", "draft_source": "def broken(:"}
        )
        self.assertFalse(result["validation"]["valid"])
        self.assertEqual(result["validation"]["issues"][0]["code"], "syntax_error")
        self.assertEqual(self.service.get("draft-flow")["draft_source"], "def broken(:")

    def test_creates_and_updates_dependencies(self):
        self.service.create({"id": "child-flow", "name": "Child", "draft_source": ""})
        result = self.service.create(
            {
                "id": "parent-flow", "name": "Parent", "draft_source": "",
                "dependencies": [{"key": "child", "target_workflow_id": "child-flow"}],
            }
        )
        self.assertEqual(result["dependencies"][0]["target_workflow_id"], "child-flow")
        with self.assertRaisesRegex(ValueError, "被其他草稿依赖"):
            self.service.delete("child-flow")
        self.service.update("parent-flow", {"name": "Parent 2", "draft_source": "", "dependencies": []})
        self.service.delete("child-flow")

    def test_rejects_bad_identifiers_missing_targets_and_self_dependency(self):
        with self.assertRaisesRegex(ValueError, "工作流 ID"):
            self.service.create({"id": "Bad ID", "name": "Bad", "draft_source": ""})
        with self.assertRaisesRegex(ValueError, "不存在"):
            self.service.create({
                "id": "parent-flow", "name": "Parent", "draft_source": "",
                "dependencies": [{"key": "missing", "target_workflow_id": "missing-flow"}],
            })

    def test_saves_visual_graph_without_replacing_code_workflows(self):
        code = self.service.create({
            "id": "code-flow", "name": "Code",
            "draft_source": "def build_workflow():\n    return None\n",
        })
        self.assertEqual(code["editor_mode"], "code")
        self.assertIsNone(code["visual_graph"])

        visual_graph = {
            "version": 1,
            "nodes": [
                {"id": "start", "type": "start", "label": "开始", "position": {"x": 0, "y": 0}},
                {
                    "id": "ask_mabel", "type": "agent", "label": "梅贝尔",
                    "position": {"x": 240, "y": 0},
                    "config": {
                        "agent_id": "mabel", "message": "处理 {message}",
                        "output": "answer",
                    },
                },
                {"id": "finish", "type": "end", "label": "结束", "position": {"x": 480, "y": 0}},
            ],
            "edges": [
                {"source": "start", "target": "ask_mabel"},
                {"source": "ask_mabel", "target": "finish"},
            ],
        }
        visual = self.service.create({
            "id": "visual-flow", "name": "Visual", "editor_mode": "visual",
            "visual_graph": visual_graph,
        })
        self.assertEqual(visual["editor_mode"], "visual")
        self.assertEqual(visual["visual_graph"]["nodes"][1]["id"], "ask_mabel")
        self.assertIn("flow.agent", visual["draft_source"])
        self.assertTrue(visual["validation"]["valid"], visual["validation"])

    def test_visual_condition_requires_named_branches(self):
        graph = self.service.visual_template()
        graph["nodes"].insert(1, {
            "id": "answer", "type": "agent", "label": "回答",
            "config": {"agent_id": "mabel", "message": "{message}", "output": "answer"},
        })
        graph["nodes"].insert(2, {
            "id": "decision", "type": "condition", "label": "判断",
            "config": {"field": "approved", "operator": "truthy"},
        })
        graph["edges"] = [
            {"source": "start", "target": "answer"},
            {"source": "answer", "target": "decision"},
            {"source": "decision", "target": "finish"},
        ]
        with self.assertRaisesRegex(ValueError, "是.*否"):
            self.service.compile_visual(graph)

    def test_visual_condition_compiles_to_native_branch(self):
        graph = {
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "classify", "type": "agent", "config": {
                    "agent_id": "mabel", "message": "判断 {message}", "output": "approved",
                }},
                {"id": "decision", "type": "condition", "config": {
                    "field": "approved", "operator": "equals", "value": "yes",
                }},
                {"id": "accept", "type": "agent", "config": {
                    "agent_id": "mabel", "message": "通过 {message}", "output": "answer",
                }},
                {"id": "reject", "type": "agent", "config": {
                    "agent_id": "analysis", "message": "拒绝 {message}", "output": "answer",
                }},
                {"id": "finish_yes", "type": "end"},
                {"id": "finish_no", "type": "end"},
            ],
            "edges": [
                {"source": "start", "target": "classify"},
                {"source": "classify", "target": "decision"},
                {"source": "decision", "target": "accept", "branch": "then"},
                {"source": "decision", "target": "reject", "branch": "otherwise"},
                {"source": "accept", "target": "finish_yes"},
                {"source": "reject", "target": "finish_no"},
            ],
        }
        compiled = self.service.compile_visual(graph)
        self.assertTrue(compiled["validation"]["valid"], compiled["validation"])
        self.assertIn("flow.if_", compiled["draft_source"])
        with self.assertRaisesRegex(ValueError, "不能依赖自身"):
            self.service.create({
                "id": "self-flow", "name": "Self", "draft_source": "",
                "dependencies": [{"key": "self-key", "target_workflow_id": "self-flow"}],
            })


class WorkflowDraftApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        service = WorkflowService(WorkflowRepository(Path(self.temp_dir.name) / "api.db"))
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(create_workflow_router(service))
        self.client = TestClient(app)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_crud_and_validation_endpoints(self):
        created = self.client.post("/api/workflows", json={
            "id": "hello-flow", "name": "Hello", "draft_source": "def build_workflow():\n    return None\n",
        })
        self.assertEqual(created.status_code, 200)
        self.assertTrue(created.json()["validation"]["valid"])
        self.assertEqual(len(self.client.get("/api/workflows").json()), 1)
        validation = self.client.post("/api/workflows/validate", json={"draft_source": "import os"})
        self.assertEqual(validation.status_code, 200)
        self.assertFalse(validation.json()["valid"])
        self.assertEqual(self.client.delete("/api/workflows/hello-flow").status_code, 200)
        self.assertEqual(self.client.get("/api/workflows/hello-flow").status_code, 404)


if __name__ == "__main__":
    unittest.main()
