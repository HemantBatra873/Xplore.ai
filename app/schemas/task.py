from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TaskBase(BaseModel):
    title: str = Field(..., description="Task title", max_length=255)
    description: Optional[str] = Field(None, description="Task description")
    status: str = Field("pending", description="Task status: pending, in_progress, completed")


class TaskCreate(TaskBase):
    """
    Create a task时的请求模型
    """

    pass


class TaskUpdate(BaseModel):
    """
    更新任务时的请求模型，允许部分更新
    """

    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None


class TaskOut(TaskBase):
    """
    返回给前端的任务响应模型
    """

    id: int
    owner_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
