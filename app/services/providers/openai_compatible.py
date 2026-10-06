"""OpenAI-compatible chat providers (OpenAI, DeepSeek, Ollama, Gemini, Anthropic, generic)."""

from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from app.services.providers.base import (
    ChatMessage,
    LLMProvider,
    LLMResult,
    LLMStreamChunk,
    ProviderConfig,
    ToolCallRequest,
)


class OpenAICompatibleProvider(LLMProvider):
    """Chat completions via the OpenAI SDK against provider-specific base URLs."""

    supports_tools = True

    def __init__(self, config: ProviderConfig):
        self.name = config.name
        self.model_name = config.model_name
        self._client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)

    def _to_payload(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for message in messages:
            item: dict[str, Any] = {"role": message.role}
            if message.content is not None:
                item["content"] = message.content
            if message.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in message.tool_calls
                ]
            if message.tool_call_id:
                item["tool_call_id"] = message.tool_call_id
            if message.name:
                item["name"] = message.name
            payload.append(item)
        return payload

    def _extract_tool_calls(self, response_message) -> list[ToolCallRequest]:
        raw = getattr(response_message, "tool_calls", None) or []
        results: list[ToolCallRequest] = []
        for tc in raw:
            fn = getattr(tc, "function", None)
            results.append(
                ToolCallRequest(
                    id=getattr(tc, "id", "") or "",
                    name=getattr(fn, "name", "") if fn else "",
                    arguments=getattr(fn, "arguments", "") if fn else "{}",
                )
            )
        return results

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
        message = response.choices[0].message
        content = message.content or ""
        usage = getattr(response, "usage", None)
        return LLMResult(
            content=content,
            model=self.model_name,
            provider=self.name,
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
            tool_calls=self._extract_tool_calls(message),
            raw=response,
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        # Streaming tool-calling is not used; orchestrator uses complete() for tool rounds.
        kwargs.pop("tools", None)
        kwargs.pop("tool_choice", None)
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
