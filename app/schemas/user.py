from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    """Shared user fields used by request and response models."""

    username: str = Field(..., min_length=3, max_length=50, description="Username")
    email: EmailStr = Field(..., description="Email address")
    full_name: Optional[str] = Field(None, description="Full name (optional)")


class UserCreate(UserBase):
    """Fields required to create a user."""

    password: str = Field(..., min_length=6, description="Password")


class UserOut(UserBase):
    """User fields returned to clients. Sensitive fields such as passwords are omitted."""

    id: int
    is_active: bool = True
    is_superuser: bool = False

    # Return provider settings without exposing the encrypted API key.
    llm_provider: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_model_name: Optional[str] = None
    has_custom_llm_key: bool = False

    model_config = ConfigDict(from_attributes=True)


class UserLLMConfigUpdate(BaseModel):
    """Payload for updating a user's custom LLM configuration."""

    llm_provider: Optional[str] = Field(None, description="LLM provider")
    llm_base_url: Optional[str] = Field(None, description="LLM Base URL")
    llm_model_name: Optional[str] = Field(None, description="LLM model name")
    llm_api_key: Optional[str] = Field(None, description="LLM API key; encrypted before storage")


class PasswordUpdate(BaseModel):
    old_password: str = Field(..., min_length=6, description="Current password")
    new_password: str = Field(..., min_length=6, description="New password")
