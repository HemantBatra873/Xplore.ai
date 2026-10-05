from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

WORKSPACE_ROLE_OWNER = "owner"
WORKSPACE_ROLE_ADMIN = "admin"
WORKSPACE_ROLE_MEMBER = "member"

WORKSPACE_ROLES = (
    WORKSPACE_ROLE_OWNER,
    WORKSPACE_ROLE_ADMIN,
    WORKSPACE_ROLE_MEMBER,
)


class Workspace(Base):
    """Tenant container for shared resources (knowledge, tasks, future agents)."""

    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    created_by = relationship("User", foreign_keys=[created_by_id], backref="created_workspaces")
    memberships = relationship(
        "WorkspaceMembership",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )


class WorkspaceMembership(Base):
    """Links a user to a workspace with a role."""

    __tablename__ = "workspace_memberships"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_membership_workspace_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, default=WORKSPACE_ROLE_MEMBER)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    workspace = relationship("Workspace", back_populates="memberships")
    user = relationship("User", backref="workspace_memberships")
