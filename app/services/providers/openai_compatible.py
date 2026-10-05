"""OpenAI-compatible chat providers (OpenAI, DeepSeek, Ollama, Gemini, Anthropic, generic)."""

from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from app.services.providers.base import (
    ChatMessage,
    LLMProvider,
    LLMResult,
    LLMStreamChunk,
    ProviderConfig,
)


class OpenAICompatibleProvider(LLMProvider):
    """Chat completions via the OpenAI SDK against provider-specific base URLs."""

    def __init__(self, config: ProviderConfig):
        self.name = config.name
        self.model_name = config.model_name
        self._client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)

    def _to_payload(self, messages: list[ChatMessage]) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> LLMResult:
        response = await self._client.chat.completions.create(
            model=self.model_name,
            messages=self._to_payload(messages),
            temperature=temperature,
            **kwargs,
        )
        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        return LLMResult(
            content=content,
            model=self.model_name,
            provider=self.name,
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
            raw=response,
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        response = await self._client.chat.completions.create(
            model=self.model_name,
            messages=self._to_payload(messages),
            temperature=temperature,
            stream=True,
            **kwargs,
        )
        async for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None) or ""
            reasoning = getattr(delta, "reasoning_content", None)
            if content or reasoning:
                yield LLMStreamChunk(content=content, reasoning=reasoning)
        yield LLMStreamChunk(done=True)
