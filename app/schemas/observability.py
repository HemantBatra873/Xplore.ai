from typing import List, Optional

from pydantic import BaseModel, Field


class LLMCallLogOut(BaseModel):
    id: int
    endpoint: str
    model_name: str
    provider: str
    request_id: Optional[str] = None
    prompt: str
    response: Optional[str] = None
    tool_calls: Optional[str] = None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    estimated_cost_usd: float
    status: str
    error_message: Optional[str] = None
    created_at: str


class DailyLLMStats(BaseModel):
    date: str
    calls: int
    tokens: int
    cost_usd: float
    avg_latency_ms: float


class EndpointLLMStats(BaseModel):
    endpoint: str
    calls: int
    tokens: int


class UserLLMStats(BaseModel):
    user_id: int
    calls: int
    tokens: int
    cost_usd: float


class LLMStatsResponse(BaseModel):
    total_calls: int = Field(..., description="Total calls")
    successful_calls: int = Field(..., description="Successful calls")
    failed_calls: int = Field(..., description="Failed calls")
    total_tokens: int = Field(..., description="Total tokens")
    total_cost_usd: float = Field(..., description="Estimated total cost in USD")
    avg_latency_ms: float = Field(..., description="Average latency in milliseconds")
    daily_stats: List[DailyLLMStats]
    endpoint_stats: List[EndpointLLMStats]
    per_user_stats: List[UserLLMStats]
