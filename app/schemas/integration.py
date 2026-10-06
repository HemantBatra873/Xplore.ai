from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class IntegrationCreate(BaseModel):
    type: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    config: dict[str, Any] = Field(default_factory=dict)
    # Write-only secrets; never echoed back
    credentials: Optional[dict[str, Any]] = None
    is_enabled: bool = True


class IntegrationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    config: Optional[dict[str, Any]] = None
    credentials: Optional[dict[str, Any]] = None
    is_enabled: Optional[bool] = None


class IntegrationOut(BaseModel):
    id: int
    workspace_id: int
    created_by_id: Optional[int] = None
    type: str
    name: str
    description: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool
    has_credentials: bool = False
    last_error: Optional[str] = None
    last_discovered_at: Optional[datetime] = None
    tool_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntegrationToolOut(BaseModel):
    id: int
    integration_id: int
    remote_name: str
    registry_name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool
    source_type: str
    integration_name: str
    discovered_at: datetime
