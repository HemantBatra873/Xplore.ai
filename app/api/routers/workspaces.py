from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.models.user import User
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceMemberCreate,
    WorkspaceMemberOut,
    WorkspaceMemberUpdate,
    WorkspaceOut,
    WorkspaceUpdate,
)
from app.services.workspace_service import WorkspaceService

router = APIRouter()


def _to_workspace_out(workspace, role: str) -> WorkspaceOut:
    return WorkspaceOut(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        created_by_id=workspace.created_by_id,
        is_active=workspace.is_active,
        role=role,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


def _to_member_out(membership, db: Session) -> WorkspaceMemberOut:
    user = db.get(User, membership.user_id)
    return WorkspaceMemberOut(
        id=membership.id,
        workspace_id=membership.workspace_id,
        user_id=membership.user_id,
        role=membership.role,
        username=user.username if user else None,
        email=user.email if user else None,
        created_at=membership.created_at,
    )


@router.post(
    "/",
    response_model=WorkspaceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workspace",
)
async def create_workspace(
    payload: WorkspaceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    workspace = WorkspaceService.create_workspace(db, user=current_user, payload=payload)
    return _to_workspace_out(workspace, "owner")


@router.get("/", response_model=list[WorkspaceOut], summary="List my workspaces")
async def list_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    WorkspaceService.ensure_default_workspace(db, current_user)
    rows = WorkspaceService.list_workspaces_for_user(db, current_user.id)
    return [_to_workspace_out(workspace, role) for workspace, role in rows]


@router.get("/{workspace_id}", response_model=WorkspaceOut, summary="Get a workspace")
async def get_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    access = WorkspaceService.get_workspace_access(db, workspace_id=workspace_id, user=current_user)
    access.require_permission("workspace:read")
    return _to_workspace_out(access.workspace, access.role)


@router.patch("/{workspace_id}", response_model=WorkspaceOut, summary="Update a workspace")
async def update_workspace(
    workspace_id: int,
    payload: WorkspaceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    access = WorkspaceService.get_workspace_access(db, workspace_id=workspace_id, user=current_user)
    workspace = WorkspaceService.update_workspace(db, access=access, payload=payload)
    return _to_workspace_out(workspace, access.role)


@router.get(
    "/{workspace_id}/members",
    response_model=list[WorkspaceMemberOut],
    summary="List workspace members",
)
async def list_members(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    access = WorkspaceService.get_workspace_access(db, workspace_id=workspace_id, user=current_user)
    members = WorkspaceService.list_members(db, access=access)
    return [_to_member_out(member, db) for member in members]


@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a workspace member",
)
async def add_member(
    workspace_id: int,
    payload: WorkspaceMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    access = WorkspaceService.get_workspace_access(db, workspace_id=workspace_id, user=current_user)
    membership = WorkspaceService.add_member(
        db, access=access, user_id=payload.user_id, role=payload.role
    )
    return _to_member_out(membership, db)


@router.patch(
    "/{workspace_id}/members/{user_id}",
    response_model=WorkspaceMemberOut,
    summary="Update a workspace member role",
)
async def update_member(
    workspace_id: int,
    user_id: int,
    payload: WorkspaceMemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    access = WorkspaceService.get_workspace_access(db, workspace_id=workspace_id, user=current_user)
    membership = WorkspaceService.update_member_role(
        db, access=access, user_id=user_id, role=payload.role
    )
    return _to_member_out(membership, db)


@router.delete(
    "/{workspace_id}/members/{user_id}",
    response_model=WorkspaceMemberOut,
    summary="Remove a workspace member",
)
async def remove_member(
    workspace_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    access = WorkspaceService.get_workspace_access(db, workspace_id=workspace_id, user=current_user)
    membership = WorkspaceService.remove_member(db, access=access, user_id=user_id)
    return _to_member_out(membership, db)
