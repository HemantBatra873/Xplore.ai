from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.workspace import WORKSPACE_ROLES


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: Optional[str] = Field(None, min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Workspace name cannot be empty")
        return cleaned


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None, min_length=1, max_length=120)
    is_active: Optional[bool] = None


class WorkspaceOut(BaseModel):
    id: int
    name: str
    slug: str
    created_by_id: int
    is_active: bool
    role: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspaceMemberCreate(BaseModel):
    user_id: int
    role: str = Field(default="member")

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        role = value.strip().lower()
        if role not in WORKSPACE_ROLES:
            raise ValueError(f"Invalid role. Expected one of: {', '.join(WORKSPACE_ROLES)}")
        return role


class WorkspaceMemberUpdate(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        role = value.strip().lower()
        if role not in WORKSPACE_ROLES:
            raise ValueError(f"Invalid role. Expected one of: {', '.join(WORKSPACE_ROLES)}")
        return role


class WorkspaceMemberOut(BaseModel):
    id: int
    workspace_id: int
    user_id: int
    role: str
    username: Optional[str] = None
    email: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
