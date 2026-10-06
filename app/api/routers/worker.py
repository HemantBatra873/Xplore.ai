from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db, get_workspace_access
from app.models.user import User
from app.services.rag_service import RAGService
from app.services.workspace_service import WorkspaceAccess
from app.utils.errors import AppException
from app.worker.celery_app import celery_app
from app.worker.tasks import process_document_task

router = APIRouter()


class DocumentProcessRequest(BaseModel):
    document_id: int


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[dict] = None


@router.post(
    "/process",
    response_model=TaskStatusResponse,
    summary="Submit an asynchronous document-processing task",
)
async def trigger_document_processing(
    request: DocumentProcessRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    """Resubmit an asynchronous processing task for one of the current workspace documents."""
    rag_service = RAGService(db)
    workspace_id = access.workspace.id
    document = rag_service.get_document_for_workspace(
        document_id=request.document_id,
        workspace_id=workspace_id,
    )
    if document is None:
        raise AppException(code=1001, msg="Document not found.", status_code=404)

    task = process_document_task.delay(request.document_id)
    document = rag_service.requeue_document(
        document_id=request.document_id,
        workspace_id=workspace_id,
        task_id=task.id,
    )

    return TaskStatusResponse(
        task_id=task.id,
        status=document.status,
        result={
            "document_id": document.id,
            "message": "Document resubmitted to the background queue. Check its status shortly.",
        },
    )


@router.get(
    "/status/{task_id}", response_model=TaskStatusResponse, summary="Get asynchronous task status"
)
async def get_task_status(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    """Get the status of a document-processing task that belongs to the current workspace."""
    rag_service = RAGService(db)
    document = rag_service.get_document_by_task_id_for_workspace(
        task_id=task_id,
        workspace_id=access.workspace.id,
    )
    if document is None:
        raise AppException(code=1001, msg="Task not found.", status_code=404)

    task_result = celery_app.AsyncResult(task_id)

    response = TaskStatusResponse(task_id=task_id, status=task_result.status)

    if task_result.status == "SUCCESS":
        response.result = task_result.result
    elif task_result.status == "FAILURE":
        response.result = {"error": str(task_result.info)}
    elif task_result.status == "PROGRESS":
        response.result = task_result.info
    else:
        response.result = {
            "document_id": document.id,
            "document_status": document.status,
        }

    return response
