"""HTTP API for workflow drafts. No submitted source is executed here."""

from fastapi import APIRouter, HTTPException

from .service import (
    DEFAULT_WORKFLOW_SOURCE,
    WorkflowConflictError,
    WorkflowNotFoundError,
    WorkflowService,
)


def create_workflow_router(service: WorkflowService | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/workflows", tags=["workflows"])
    workflow_service = service or WorkflowService()

    def handle(exc: ValueError) -> HTTPException:
        if isinstance(exc, WorkflowNotFoundError):
            return HTTPException(404, str(exc))
        if isinstance(exc, WorkflowConflictError):
            return HTTPException(409, str(exc))
        return HTTPException(400, str(exc))

    @router.get("")
    def list_workflows():
        return workflow_service.list()

    @router.get("/template")
    def workflow_template():
        return {"draft_source": DEFAULT_WORKFLOW_SOURCE}

    @router.post("/validate")
    def validate_workflow(payload: dict):
        try:
            return workflow_service.validate(payload.get("draft_source"))
        except ValueError as exc:
            raise handle(exc)

    @router.post("")
    def create_workflow(payload: dict):
        try:
            return workflow_service.create(payload)
        except ValueError as exc:
            raise handle(exc)

    @router.get("/{workflow_id}")
    def get_workflow(workflow_id: str):
        try:
            return workflow_service.get(workflow_id)
        except ValueError as exc:
            raise handle(exc)

    @router.put("/{workflow_id}")
    def update_workflow(workflow_id: str, payload: dict):
        try:
            return workflow_service.update(workflow_id, payload)
        except ValueError as exc:
            raise handle(exc)

    @router.delete("/{workflow_id}")
    def delete_workflow(workflow_id: str):
        try:
            workflow_service.delete(workflow_id)
            return {"deleted": True}
        except ValueError as exc:
            raise handle(exc)

    return router
