"""LLM provider factory unit tests (no network)."""

from app.core.config import settings
from app.services.providers.factory import (
    PROVIDER_DEFAULTS,
    get_llm_provider,
    resolve_provider_name,
)
from app.services.providers.mock import MockLLMProvider
from app.services.providers.openai_compatible import OpenAICompatibleProvider


def test_resolve_provider_aliases():
    assert resolve_provider_name("google") == "gemini"
    assert resolve_provider_name("claude") == "anthropic"
    assert resolve_provider_name("local") == "ollama"
    assert resolve_provider_name("openai") == "openai"


def test_supported_provider_defaults_exist():
    for name in ("openai", "anthropic", "gemini", "deepseek", "ollama", "openai_compatible"):
        assert name in PROVIDER_DEFAULTS
        assert "base_url" in PROVIDER_DEFAULTS[name]
        assert "default_model" in PROVIDER_DEFAULTS[name]


def test_get_llm_provider_returns_mock_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "LLM_MOCK", True)
    provider = get_llm_provider(None)
    assert isinstance(provider, MockLLMProvider)


def test_get_llm_provider_openai_compatible_when_not_mock(monkeypatch):
    monkeypatch.setattr(settings, "LLM_MOCK", False)
    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "")
    monkeypatch.setattr(settings, "LLM_MODEL_NAME", "")
    provider = get_llm_provider(None)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.name == "openai"
    assert provider.model_name == PROVIDER_DEFAULTS["openai"]["default_model"]
