from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., description="User input message", min_length=1)
    stream: bool = Field(False, description="Whether to use SSE streaming")


class ChatResponse(BaseModel):
    reply: str = Field(..., description="LLM response")
