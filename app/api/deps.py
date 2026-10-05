from typing import Generator

import jwt
from fastapi import Depends, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.auth import TokenPayload
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
        # Decode JWT
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

    # Load user row
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
