from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class LLMResult:
    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    raw: Any = None


@dataclass
class LLMStreamChunk:
    content: str = ""
    reasoning: Optional[str] = None
    done: bool = False


@dataclass
class ProviderConfig:
    name: str
    api_key: str
    base_url: str
    model_name: str
    extra: dict = field(default_factory=dict)


class LLMProvider(ABC):
    """Provider-agnostic chat completion interface."""

    name: str

    @abstractmethod
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> LLMResult:
        raise NotImplementedError

    @abstractmethod
    def stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        raise NotImplementedError
