from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TaskBase(BaseModel):
    title: str = Field(..., description="Task title", max_length=255)
    description: Optional[str] = Field(None, description="Task description")
    status: str = Field("pending", description="Task status: pending, in_progress, completed")


class TaskCreate(TaskBase):
    """Request model for creating a task."""

    pass


class TaskUpdate(BaseModel):
    """Request model for partially updating a task."""

    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None


class TaskOut(TaskBase):
    """Task response model returned to clients."""

    id: int
    owner_id: int
    workspace_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
