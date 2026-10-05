from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.knowledge import CitationSource


class DocumentResponse(BaseModel):
    id: int
    filename: str
    file_type: str
    status: str
    chunks_count: int
    workspace_id: Optional[int] = None
    knowledge_base_id: Optional[int] = None
    processing_task_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RAGQueryRequest(BaseModel):
    query: str
    top_k: int = Field(3, ge=1, le=10)
    session_id: Optional[str] = Field(None, description="Session ID for multi-turn context")
    knowledge_base_id: Optional[int] = None
    enable_rerank: Optional[bool] = None
    enable_hybrid: Optional[bool] = None


class RAGQueryResponse(BaseModel):
    query: str
    answer: str
    sources: List[CitationSource] = []
    source_chunks: List[str] = []
