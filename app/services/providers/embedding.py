"""Embedding provider separated from conversational LLM providers."""

from typing import Optional

from openai import AsyncOpenAI

from app.core.config import settings

_embedding_client: Optional[AsyncOpenAI] = None


class EmbeddingProvider:
    """OpenAI-compatible embedding client (Ollama / local / remote)."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self.api_key = api_key or settings.EMBEDDING_API_KEY
        self.base_url = base_url or settings.EMBEDDING_BASE_URL
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        cleaned = [text.replace("\n", " ") for text in texts]
        response = await self._client.embeddings.create(input=cleaned, model=self.model_name)
        return [item.embedding for item in response.data]


def get_embedding_provider() -> EmbeddingProvider:
    global _embedding_client
    # Keep a module-level provider for reuse (same pattern as prior singleton client)
    if not hasattr(get_embedding_provider, "_provider"):
        get_embedding_provider._provider = EmbeddingProvider()  # type: ignore[attr-defined]
    return get_embedding_provider._provider  # type: ignore[attr-defined]
