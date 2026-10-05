from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """
    User ORM model (users table).
    """

    __tablename__ = "users"

    # SQLAlchemy 2.0 Mapped / mapped_column
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Password hash only; never store plaintext passwords.
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)

    # Preferred workspace for clients that omit X-Workspace-Id
    default_workspace_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("workspaces.id", use_alter=True, name="fk_users_default_workspace_id"), nullable=True
    )

    # Optional per-user LLM settings (multi-tenant BYOK)
    llm_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    llm_base_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    llm_model_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    llm_api_key_encrypted: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    @property
    def has_custom_llm_key(self) -> bool:
        return bool(self.llm_api_key_encrypted)
