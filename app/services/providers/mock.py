import asyncio
from typing import Any, AsyncIterator

from app.services.providers.base import (
    ChatMessage,
    LLMProvider,
    LLMResult,
    LLMStreamChunk,
)


class MockLLMProvider(LLMProvider):
    """Offline provider that returns preset replies without an API key."""

    name = "mock"
    supports_tools = False

    def __init__(self, model_name: str = "mock-model"):
        self.model_name = model_name

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> LLMResult:
        return LLMResult(
            content=(
                "This is a mock response. Xplore.ai is running offline without a live LLM provider."
            ),
            model=self.model_name,
            provider=self.name,
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        content = "This is a streamed mock response. Xplore.ai is running offline without a live LLM provider."
        for char in content:
            yield LLMStreamChunk(content=char)
            await asyncio.sleep(0.01)
        yield LLMStreamChunk(done=True)
