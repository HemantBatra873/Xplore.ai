from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.task import TaskCreate, TaskOut, TaskUpdate
from app.services.task_service import TaskService

router = APIRouter()


@router.post("/", response_model=TaskOut, status_code=status.HTTP_201_CREATED, summary="Create a task")
async def create_task(
    task_in: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new task owned by the current user."""
    return TaskService.create_task(db, task_in, owner_id=current_user.id)


@router.get("/", response_model=List[TaskOut], summary="List the current user tasks")
async def list_tasks(
    skip: int = Query(0, description="Number of records to skip"),
    limit: int = Query(100, description="Maximum number of records to return", le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the current user's tasks with optional pagination."""
    return TaskService.list_tasks(db, owner_id=current_user.id, skip=skip, limit=limit)


@router.get("/{task_id}", response_model=TaskOut, summary="Get task details")
async def get_task(
    task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Get a single task that belongs to the current user."""
    return TaskService.get_task(db, task_id, owner_id=current_user.id)


@router.put("/{task_id}", response_model=TaskOut, summary="Update task")
async def update_task(
    task_id: int,
    task_in: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a task title, description, or status."""
    return TaskService.update_task(db, task_id, owner_id=current_user.id, task_in=task_in)


@router.delete("/{task_id}", response_model=TaskOut, summary="Delete a task")
async def delete_task(
    task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Delete a task that belongs to the current user."""
    return TaskService.delete_task(db, task_id, owner_id=current_user.id)
