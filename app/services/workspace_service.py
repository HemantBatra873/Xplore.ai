import re
from dataclasses import dataclass
from typing import Optional

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workspace import (
    WORKSPACE_ROLE_MEMBER,
    WORKSPACE_ROLE_OWNER,
    Workspace,
    WorkspaceMembership,
)
from app.schemas.workspace import WorkspaceCreate, WorkspaceUpdate
from app.services.workspace_permissions import (
    can_assign_role,
    can_manage_member,
    has_permission,
    normalize_role,
)
from app.utils.errors import AppException


@dataclass
class WorkspaceAccess:
    workspace: Workspace
    membership: WorkspaceMembership

    @property
    def role(self) -> str:
        return self.membership.role

    def require_permission(self, permission: str) -> None:
        if not has_permission(self.role, permission):
            raise AppException(
                code=1007,
                msg="You do not have permission to perform this action in this workspace",
                status_code=status.HTTP_403_FORBIDDEN,
            )


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "workspace"


class WorkspaceService:
    @staticmethod
    def _unique_slug(db: Session, base: str, *, exclude_id: Optional[int] = None) -> str:
        candidate = slugify(base)[:100]
        suffix = 0
        while True:
            slug = candidate if suffix == 0 else f"{candidate}-{suffix}"
            stmt = select(Workspace).where(Workspace.slug == slug)
            if exclude_id is not None:
                stmt = stmt.where(Workspace.id != exclude_id)
            exists = db.execute(stmt).scalar_one_or_none()
            if exists is None:
                return slug
            suffix += 1

    @classmethod
    def create_personal_workspace(cls, db: Session, user: User, *, commit: bool = True) -> Workspace:
        """Create a default personal workspace and owner membership for a user."""
        name = f"{user.username}'s Workspace"
        workspace = Workspace(
            name=name,
            slug=cls._unique_slug(db, f"user-{user.id}-{user.username}"),
            created_by_id=user.id,
            is_active=True,
        )
        db.add(workspace)
        db.flush()

        membership = WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user.id,
            role=WORKSPACE_ROLE_OWNER,
        )
        db.add(membership)

        user.default_workspace_id = workspace.id
        if commit:
            db.commit()
            db.refresh(workspace)
        return workspace

    @classmethod
    def ensure_default_workspace(cls, db: Session, user: User) -> Workspace:
        if user.default_workspace_id:
            workspace = db.get(Workspace, user.default_workspace_id)
            if workspace and workspace.is_active:
                return workspace

        membership = db.execute(
            select(WorkspaceMembership)
            .where(WorkspaceMembership.user_id == user.id)
            .order_by(WorkspaceMembership.created_at.asc())
        ).scalar_one_or_none()
        if membership:
            workspace = db.get(Workspace, membership.workspace_id)
            if workspace:
                user.default_workspace_id = workspace.id
                db.commit()
                return workspace

        return cls.create_personal_workspace(db, user)

    @classmethod
    def create_workspace(
        cls, db: Session, *, user: User, payload: WorkspaceCreate
    ) -> Workspace:
        workspace = Workspace(
            name=payload.name.strip(),
            slug=cls._unique_slug(db, payload.slug or payload.name),
            created_by_id=user.id,
            is_active=True,
        )
        db.add(workspace)
        db.flush()
        db.add(
            WorkspaceMembership(
                workspace_id=workspace.id,
                user_id=user.id,
                role=WORKSPACE_ROLE_OWNER,
            )
        )
        if user.default_workspace_id is None:
            user.default_workspace_id = workspace.id
        db.commit()
        db.refresh(workspace)
        return workspace

    @classmethod
    def list_workspaces_for_user(cls, db: Session, user_id: int) -> list[tuple[Workspace, str]]:
        rows = db.execute(
            select(Workspace, WorkspaceMembership.role)
            .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
            .where(
                WorkspaceMembership.user_id == user_id,
                Workspace.is_active.is_(True),
            )
            .order_by(Workspace.created_at.asc())
        ).all()
        return [(workspace, role) for workspace, role in rows]

    @classmethod
    def get_membership(
        cls, db: Session, *, workspace_id: int, user_id: int
    ) -> Optional[WorkspaceMembership]:
        return db.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
            )
        ).scalar_one_or_none()

    @classmethod
    def get_workspace_access(
        cls, db: Session, *, workspace_id: int, user: User
    ) -> WorkspaceAccess:
        workspace = db.get(Workspace, workspace_id)
        if workspace is None or not workspace.is_active:
            raise AppException(
                code=10404,
                msg="Workspace not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        membership = cls.get_membership(db, workspace_id=workspace_id, user_id=user.id)
        if membership is None:
            raise AppException(
                code=10403,
                msg="You are not a member of this workspace",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return WorkspaceAccess(workspace=workspace, membership=membership)

    @classmethod
    def update_workspace(
        cls, db: Session, *, access: WorkspaceAccess, payload: WorkspaceUpdate
    ) -> Workspace:
        access.require_permission("workspace:update")
        workspace = access.workspace
        data = payload.model_dump(exclude_unset=True)
        if "name" in data and data["name"] is not None:
            workspace.name = data["name"].strip()
        if "slug" in data and data["slug"] is not None:
            workspace.slug = cls._unique_slug(db, data["slug"], exclude_id=workspace.id)
        if "is_active" in data and data["is_active"] is not None:
            access.require_permission("workspace:delete")
            workspace.is_active = data["is_active"]
        db.commit()
        db.refresh(workspace)
        return workspace

    @classmethod
    def list_members(cls, db: Session, *, access: WorkspaceAccess) -> list[WorkspaceMembership]:
        access.require_permission("members:read")
        return list(
            db.execute(
                select(WorkspaceMembership)
                .where(WorkspaceMembership.workspace_id == access.workspace.id)
                .order_by(WorkspaceMembership.created_at.asc())
            )
            .scalars()
            .all()
        )

    @classmethod
    def add_member(
        cls,
        db: Session,
        *,
        access: WorkspaceAccess,
        user_id: int,
        role: str = WORKSPACE_ROLE_MEMBER,
    ) -> WorkspaceMembership:
        access.require_permission("members:invite")
        role = normalize_role(role)
        if not can_assign_role(access.role, role):
            raise AppException(
                code=1007,
                msg="You cannot assign this role",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        target = db.get(User, user_id)
        if target is None or not target.is_active:
            raise AppException(
                code=1002, msg="User not found", status_code=status.HTTP_404_NOT_FOUND
            )

        existing = cls.get_membership(
            db, workspace_id=access.workspace.id, user_id=user_id
        )
        if existing:
            raise AppException(
                code=10409,
                msg="User is already a member of this workspace",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        membership = WorkspaceMembership(
            workspace_id=access.workspace.id,
            user_id=user_id,
            role=role,
        )
        db.add(membership)
        db.commit()
        db.refresh(membership)
        return membership

    @classmethod
    def update_member_role(
        cls,
        db: Session,
        *,
        access: WorkspaceAccess,
        user_id: int,
        role: str,
    ) -> WorkspaceMembership:
        access.require_permission("members:manage")
        role = normalize_role(role)
        membership = cls.get_membership(
            db, workspace_id=access.workspace.id, user_id=user_id
        )
        if membership is None:
            raise AppException(
                code=10404,
                msg="Membership not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if not can_manage_member(access.role, membership.role):
            raise AppException(
                code=1007,
                msg="You cannot manage this member",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if not can_assign_role(access.role, role):
            raise AppException(
                code=1007,
                msg="You cannot assign this role",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if membership.role == WORKSPACE_ROLE_OWNER and role != WORKSPACE_ROLE_OWNER:
            owner_count = db.execute(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == access.workspace.id,
                    WorkspaceMembership.role == WORKSPACE_ROLE_OWNER,
                )
            ).scalars().all()
            if len(owner_count) <= 1:
                raise AppException(
                    code=10410,
                    msg="A workspace must keep at least one owner",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        membership.role = role
        db.commit()
        db.refresh(membership)
        return membership

    @classmethod
    def remove_member(
        cls, db: Session, *, access: WorkspaceAccess, user_id: int
    ) -> WorkspaceMembership:
        access.require_permission("members:remove")
        membership = cls.get_membership(
            db, workspace_id=access.workspace.id, user_id=user_id
        )
        if membership is None:
            raise AppException(
                code=10404,
                msg="Membership not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if not can_manage_member(access.role, membership.role):
            raise AppException(
                code=1007,
                msg="You cannot remove this member",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if membership.role == WORKSPACE_ROLE_OWNER:
            owners = db.execute(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == access.workspace.id,
                    WorkspaceMembership.role == WORKSPACE_ROLE_OWNER,
                )
            ).scalars().all()
            if len(owners) <= 1:
                raise AppException(
                    code=10410,
                    msg="A workspace must keep at least one owner",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        db.delete(membership)
        target_user = db.get(User, user_id)
        if target_user and target_user.default_workspace_id == access.workspace.id:
            target_user.default_workspace_id = None
        db.commit()
        return membership
