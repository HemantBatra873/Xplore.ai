from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

INTEGRATION_TYPE_MCP = "mcp"
INTEGRATION_TYPE_GITHUB = "github"
INTEGRATION_TYPES = (INTEGRATION_TYPE_MCP, INTEGRATION_TYPE_GITHUB)

MCP_TRANSPORT_HTTP = "http"
MCP_TRANSPORTS = (MCP_TRANSPORT_HTTP,)


class Integration(Base):
    """Workspace-scoped external integration (MCP server, GitHub, etc.)."""

    __tablename__ = "integrations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_integrations_workspace_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Non-secret configuration JSON (endpoint, transport, owner filters, etc.)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # Encrypted JSON blob for secrets (tokens, headers). Never serialize to API.
    credentials_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_discovered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    workspace = relationship("Workspace", backref="integrations")
    created_by = relationship("User", backref="created_integrations")
    discovered_tools = relationship(
        "IntegrationTool",
        back_populates="integration",
        cascade="all, delete-orphan",
    )


class IntegrationTool(Base):
    """Cached/normalized tool definitions discovered from an integration."""

    __tablename__ = "integration_tools"
    __table_args__ = (
        UniqueConstraint(
            "integration_id", "remote_name", name="uq_integration_tools_integration_remote"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    integration_id: Mapped[int] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    remote_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Registry name exposed to agents: ext:{integration_id}:{remote_name}
    registry_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_schema_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    integration = relationship("Integration", back_populates="discovered_tools")
