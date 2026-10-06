from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_workspace_access
from app.models.user import User
from app.schemas.integration import (
    IntegrationCreate,
    IntegrationOut,
    IntegrationToolOut,
    IntegrationUpdate,
)
from app.services.integration_service import IntegrationService
from app.services.integrations import supported_integration_types
from app.services.workspace_service import WorkspaceAccess

router = APIRouter()


def _current_user(db: Session, access: WorkspaceAccess) -> User:
    user = db.get(User, access.membership.user_id)
    if user is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.get("/types", summary="List supported integration types")
async def list_types(access: WorkspaceAccess = Depends(get_workspace_access)):
    access.require_permission("integrations:read")
    return {"types": supported_integration_types()}


@router.get("/", response_model=list[IntegrationOut], summary="List integrations")
async def list_integrations(
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("integrations:read")
    rows = IntegrationService.list_for_workspace(db, workspace_id=access.workspace.id)
    return [IntegrationOut(**IntegrationService.to_out(row)) for row in rows]


@router.post(
    "/",
    response_model=IntegrationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an integration",
)
async def create_integration(
    payload: IntegrationCreate,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    user = _current_user(db, access)
    integration = IntegrationService.create(
        db, access=access, payload=payload, created_by_id=user.id
    )
    return IntegrationOut(**IntegrationService.to_out(integration))


@router.get(
    "/{integration_id}",
    response_model=IntegrationOut,
    summary="Get an integration",
)
async def get_integration(
    integration_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("integrations:read")
    integration = IntegrationService.get_for_workspace(
        db, integration_id=integration_id, workspace_id=access.workspace.id
    )
    return IntegrationOut(**IntegrationService.to_out(integration))


@router.put(
    "/{integration_id}",
    response_model=IntegrationOut,
    summary="Update an integration",
)
@router.patch(
    "/{integration_id}",
    response_model=IntegrationOut,
    summary="Update an integration",
)
async def update_integration(
    integration_id: int,
    payload: IntegrationUpdate,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    integration = IntegrationService.update(
        db, access=access, integration_id=integration_id, payload=payload
    )
    return IntegrationOut(**IntegrationService.to_out(integration))


@router.delete("/{integration_id}", summary="Delete an integration")
async def delete_integration(
    integration_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    integration = IntegrationService.delete(db, access=access, integration_id=integration_id)
    return JSONResponse(
        content={"message": "Integration deleted", "integration_id": integration.id}
    )


@router.post(
    "/{integration_id}/connect",
    response_model=IntegrationOut,
    summary="Connect and discover tools",
)
async def connect_integration(
    integration_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    integration = IntegrationService.connect(db, access=access, integration_id=integration_id)
    return IntegrationOut(**IntegrationService.to_out(integration))


@router.post(
    "/{integration_id}/refresh-tools",
    response_model=IntegrationOut,
    summary="Refresh discovered tools",
)
async def refresh_tools(
    integration_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    integration = IntegrationService.refresh_tools(db, access=access, integration_id=integration_id)
    return IntegrationOut(**IntegrationService.to_out(integration))


@router.get(
    "/{integration_id}/tools",
    response_model=list[IntegrationToolOut],
    summary="List discovered tools for an integration",
)
async def list_integration_tools(
    integration_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    pairs = IntegrationService.list_tools(db, access=access, integration_id=integration_id)
    return [
        IntegrationToolOut(**IntegrationService.tool_to_out(integration, tool))
        for integration, tool in pairs
    ]
