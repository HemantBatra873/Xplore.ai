from typing import Generator, Optional

import jwt
from fastapi import Depends, Header, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.auth import TokenPayload
from app.services.workspace_service import WorkspaceAccess, WorkspaceService
from app.utils.errors import AppException

# OAuth2 token URL for clients
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_db() -> Generator:
    """
    Yield a DB session per request; closed after the request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    """
    Resolve the current user from the JWT:
    1. Read Bearer token
    2. Validate signature and expiry
    3. Load User by id from the database
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        token_data = TokenPayload(**payload)
    except (jwt.PyJWTError, ValidationError):
        raise AppException(
            code=1003,
            msg="Could not validate credentials (invalid or expired token)",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if not token_data.sub:
        raise AppException(
            code=1003, msg="Invalid token payload", status_code=status.HTTP_401_UNAUTHORIZED
        )

    user = db.get(User, int(token_data.sub))
    if not user:
        raise AppException(code=1004, msg="User not found", status_code=status.HTTP_404_NOT_FOUND)

    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Require an active user account.
    """
    if not current_user.is_active:
        raise AppException(code=1006, msg="Inactive user", status_code=status.HTTP_400_BAD_REQUEST)
    return current_user


def get_current_active_superuser(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Require a superuser.
    """
    if not current_user.is_superuser:
        raise AppException(
            code=1007,
            msg="The user doesn't have enough privileges",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return current_user


def get_workspace_access(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    x_workspace_id: Optional[str] = Header(default=None, alias="X-Workspace-Id"),
) -> WorkspaceAccess:
    """
    Resolve the active workspace for the request.

    Clients should send X-Workspace-Id. When omitted, the user's default
    workspace is used for compatibility with existing clients.
    """
    workspace_id: Optional[int] = None
    if x_workspace_id is not None and str(x_workspace_id).strip() != "":
        try:
            workspace_id = int(x_workspace_id)
        except (TypeError, ValueError):
            raise AppException(
                code=10400,
                msg="Invalid X-Workspace-Id header",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    if workspace_id is None:
        workspace = WorkspaceService.ensure_default_workspace(db, current_user)
        workspace_id = workspace.id

    return WorkspaceService.get_workspace_access(
        db, workspace_id=workspace_id, user=current_user
    )


def require_workspace_permission(permission: str):
    """Dependency factory that checks a named workspace permission."""

    def _dependency(access: WorkspaceAccess = Depends(get_workspace_access)) -> WorkspaceAccess:
        access.require_permission(permission)
        return access

    return _dependency
