from typing import Optional

from pydantic import BaseModel, field_validator


class Token(BaseModel):
    """Access token returned after a successful sign-in."""

    access_token: str
    token_type: str


class TokenPayload(BaseModel):
    """Internal JWT payload used when decoding tokens."""

    sub: Optional[str] = None


class SetupStatus(BaseModel):
    """Whether the system has completed initial setup."""

    initialized: bool
    llm_mock: bool
    llm_provider: str


class SetupRequest(BaseModel):
    """Payload for creating the first administrator during setup."""

    username: str
    email: str
    password: str
    full_name: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_model_name: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("Invalid email address")
        return v
