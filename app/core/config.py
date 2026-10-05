from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Global application settings.
    Loaded from .env and environment via pydantic-settings.
    """

    # Project metadata
    PROJECT_NAME: str = "Xplore.ai"
    VERSION: str = "0.1.0"
    TESTING: bool = False

    # Database
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/xplore_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:8000"

    # Logging
    LOG_FORMAT: str = "text"  # text | json

    # JWT auth
    SECRET_KEY: str = "replace_with_a_long_random_secret_key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # LLM (defaults are placeholders; override via .env)
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_MODEL_NAME: str = "deepseek-chat"
    LLM_PROVIDER: str = "deepseek"
    LLM_INPUT_PRICE_PER_1K_TOKENS: float = 0.0
    LLM_OUTPUT_PRICE_PER_1K_TOKENS: float = 0.0

    # Mock mode — preset LLM replies without an API key
    LLM_MOCK: bool = False

    # Embeddings (separate from LLM; defaults to local Ollama)
    EMBEDDING_BASE_URL: str = "http://localhost:11434/v1"
    EMBEDDING_API_KEY: str = "ollama"
    EMBEDDING_MODEL_NAME: str = "bge-m3"

    # Ollama base URL (health checks, etc.)
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"

    # RAG
    EMBEDDING_DIMENSION: int = 1024

    @model_validator(mode="after")
    def _auto_enable_mock(self) -> "Settings":
        """Enable mock mode automatically when LLM_API_KEY is empty."""
        if not self.LLM_API_KEY and not self.LLM_MOCK:
            import logging

            logging.getLogger(__name__).warning(
                "LLM_API_KEY is empty, so mock mode has been enabled. "
                "Set LLM_API_KEY or LLM_MOCK=false to change this behavior."
            )
            self.LLM_MOCK = True
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Ignore extra .env keys not defined on Settings
    )


# Global settings instance for the application
settings = Settings()
