from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    system_prompt: str = Field(
        "You are a helpful assistant for Xplore.ai.", min_length=1, max_length=20000
    )
    provider: Optional[str] = Field(None, max_length=50)
    model_name: Optional[str] = Field(None, max_length=100)
    is_enabled: bool = True
    knowledge_base_ids: List[int] = []
    enabled_tools: List[str] = []


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    system_prompt: Optional[str] = Field(None, min_length=1, max_length=20000)
    provider: Optional[str] = Field(None, max_length=50)
    model_name: Optional[str] = Field(None, max_length=100)
    is_enabled: Optional[bool] = None
    knowledge_base_ids: Optional[List[int]] = None
    enabled_tools: Optional[List[str]] = None


class AgentOut(BaseModel):
    id: int
    workspace_id: int
    created_by_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    system_prompt: str
    provider: Optional[str] = None
    model_name: Optional[str] = None
    is_enabled: bool
    knowledge_base_ids: List[int] = []
    enabled_tools: List[str] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ToolInfoOut(BaseModel):
    name: str
    description: str
    input_schema: dict
    requires_workspace: bool = False
    requires_user: bool = False
    enabled: bool = True


class AgentKnowledgeUpdate(BaseModel):
    knowledge_base_ids: List[int] = []


class AgentToolsUpdate(BaseModel):
    enabled_tools: List[str] = []
