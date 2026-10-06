from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_workspace_access
from app.schemas.task import TaskCreate, TaskOut, TaskUpdate
from app.services.task_service import TaskService
from app.services.workspace_service import WorkspaceAccess

router = APIRouter()


@router.post(
    "/", response_model=TaskOut, status_code=status.HTTP_201_CREATED, summary="Create a task"
)
async def create_task(
    task_in: TaskCreate,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    """Create a new task in the current workspace."""
    access.require_permission("resources:write")
    return TaskService.create_task(
        db,
        task_in,
        owner_id=access.membership.user_id,
        workspace_id=access.workspace.id,
    )


@router.get("/", response_model=List[TaskOut], summary="List the current workspace tasks")
async def list_tasks(
    skip: int = Query(0, description="Number of records to skip"),
    limit: int = Query(100, description="Maximum number of records to return", le=100),
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    """List tasks for the current workspace with optional pagination."""
    access.require_permission("resources:read")
    return TaskService.list_tasks(db, workspace_id=access.workspace.id, skip=skip, limit=limit)


@router.get("/{task_id}", response_model=TaskOut, summary="Get task details")
async def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    """Get a single task that belongs to the current workspace."""
    access.require_permission("resources:read")
    return TaskService.get_task(db, task_id, workspace_id=access.workspace.id)


@router.put("/{task_id}", response_model=TaskOut, summary="Update task")
async def update_task(
    task_id: int,
    task_in: TaskUpdate,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    """Update a task title, description, or status."""
    access.require_permission("resources:write")
    return TaskService.update_task(db, task_id, workspace_id=access.workspace.id, task_in=task_in)


@router.delete("/{task_id}", response_model=TaskOut, summary="Delete a task")
async def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    """Delete a task that belongs to the current workspace."""
    access.require_permission("resources:write")
    return TaskService.delete_task(db, task_id, workspace_id=access.workspace.id)
