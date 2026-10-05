from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.knowledge import CitationSource


class ConversationCreate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    use_knowledge: bool = False
    knowledge_base_ids: Optional[List[int]] = None


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    use_knowledge: Optional[bool] = None
    knowledge_base_ids: Optional[List[int]] = None


class ConversationOut(BaseModel):
    id: int
    workspace_id: int
    created_by_id: int
    title: str
    use_knowledge: bool
    knowledge_base_ids: List[int] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageCitationOut(CitationSource):
    id: Optional[int] = None


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    status: str
    error_message: Optional[str] = None
    citations: List[MessageCitationOut] = []
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailOut(ConversationOut):
    messages: List[MessageOut] = []


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1)
    # Per-request overrides (optional); fall back to conversation settings
    use_knowledge: Optional[bool] = None
    knowledge_base_ids: Optional[List[int]] = None
    top_k: int = Field(3, ge=1, le=10)
    enable_rerank: Optional[bool] = None
    enable_hybrid: Optional[bool] = None


class SendMessageResponse(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
    sources: List[CitationSource] = []
