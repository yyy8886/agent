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
