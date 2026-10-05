from typing import Optional

from app.core.config import settings
from app.core.logging import logger
from app.models.user import User
from app.services.providers.base import LLMProvider, ProviderConfig
from app.services.providers.mock import MockLLMProvider
from app.services.providers.openai_compatible import OpenAICompatibleProvider
from app.utils.encryption import decrypt_api_key

# Default OpenAI-compatible endpoints and models per provider name.
PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    "anthropic": {
        # Anthropic OpenAI-compatible Messages API surface when available
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-3-5-sonnet-latest",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.0-flash",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3.2",
    },
    "openai_compatible": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "gpt-4o-mini",
    },
}

SUPPORTED_PROVIDERS = tuple(PROVIDER_DEFAULTS.keys()) + ("mock",)


def resolve_provider_name(name: Optional[str]) -> str:
    value = (name or settings.LLM_PROVIDER or "openai_compatible").strip().lower()
    aliases = {
        "google": "gemini",
        "google-gemini": "gemini",
        "claude": "anthropic",
        "compatible": "openai_compatible",
        "local": "ollama",
    }
    value = aliases.get(value, value)
    if value not in PROVIDER_DEFAULTS and value != "mock":
        logger.warning(f"Unknown LLM provider '{value}', using openai_compatible defaults")
        return "openai_compatible"
    return value


def _defaults_for(provider: str) -> dict[str, str]:
    return PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["openai_compatible"])


def get_llm_provider(user: Optional[User] = None) -> LLMProvider:
    """
    Resolve an LLMProvider for the current user / global settings.
    Provider-specific defaults apply when base_url or model are omitted.
    """
    if settings.LLM_MOCK:
        logger.info("==> LLM mock mode is enabled; using the mock provider")
        return MockLLMProvider()

    provider_name = resolve_provider_name(
        user.llm_provider if user and user.llm_provider else settings.LLM_PROVIDER
    )
    defaults = _defaults_for(provider_name)

    api_key = settings.LLM_API_KEY
    base_url = settings.LLM_BASE_URL or defaults["base_url"]
    model_name = settings.LLM_MODEL_NAME or defaults["default_model"]

    if user and user.has_custom_llm_key:
        try:
            api_key = decrypt_api_key(user.llm_api_key_encrypted)
            provider_name = resolve_provider_name(user.llm_provider or provider_name)
            defaults = _defaults_for(provider_name)
            base_url = user.llm_base_url or defaults["base_url"]
            model_name = user.llm_model_name or defaults["default_model"]
        except Exception as exc:
            logger.warning(
                f"Unable to decrypt the custom LLM key for user {user.id}; "
                f"using the global configuration: {exc}"
            )

    # Ollama often accepts any non-empty key
    if provider_name == "ollama" and not api_key:
        api_key = "ollama"

    config = ProviderConfig(
        name=provider_name,
        api_key=api_key or "unused",
        base_url=base_url,
        model_name=model_name,
    )
    return OpenAICompatibleProvider(config)
