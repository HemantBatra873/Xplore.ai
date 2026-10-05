from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)


class KnowledgeBaseOut(BaseModel):
    id: int
    workspace_id: int
    name: str
    description: Optional[str] = None
    created_by_id: Optional[int] = None
    document_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CitationSource(BaseModel):
    chunk_id: int
    document_id: int
    knowledge_base_id: int
    knowledge_base_name: Optional[str] = None
    filename: str
    chunk_index: int
    excerpt: str
    score: Optional[float] = None
    vector_score: Optional[float] = None
    keyword_score: Optional[float] = None


class KnowledgeQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(3, ge=1, le=10)
    knowledge_base_id: Optional[int] = None
    session_id: Optional[str] = None
    enable_rerank: Optional[bool] = None
    enable_hybrid: Optional[bool] = None


class KnowledgeQueryResponse(BaseModel):
    query: str
    answer: str
    sources: List[CitationSource]
    # Backward-compatible aliases for older clients
    source_chunks: List[str] = []
