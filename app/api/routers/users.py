from typing import List

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_superuser, get_current_active_user, get_db
from app.utils.errors import AppException
from app.core.config import settings
from app.models.user import User
from app.schemas.user import PasswordUpdate, UserCreate, UserLLMConfigUpdate, UserOut
from app.services.user_service import UserService
from app.utils.rate_limit import RateLimiter

router = APIRouter()

# Registration rate limit: 5 sign-ups per hour per IP (disabled in tests)
register_limiter = RateLimiter(times=5, seconds=3600) if not settings.TESTING else None


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="Create a user")
async def create_user(user_in: UserCreate, request: Request, db: Session = Depends(get_db)):
    """Register a new user. Rate limited to 5 registrations per IP per hour."""
    if register_limiter:
        await register_limiter(request)
    return UserService.create_user(db, user_in)


@router.get("/me", response_model=UserOut, summary="Get the current user")
async def get_user_me(current_user: User = Depends(get_current_active_user)):
    """Return the authenticated user. Requires Authorization: Bearer <token>."""
    return current_user


@router.put("/me/llm-config", response_model=UserOut, summary="Update the current user LLM configuration")
async def update_user_llm_config(
    config_in: UserLLMConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update the current user's LLM provider settings. API keys are encrypted at rest."""
    return UserService.update_llm_config(db, current_user.id, config_in)


@router.put("/me/password", response_model=UserOut, summary="Change the current user password")
async def change_password(
    password_in: PasswordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return UserService.change_password(db, current_user.id, password_in)


@router.get("/{user_id}", response_model=UserOut, summary="Get user details")
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not current_user.is_superuser and user_id != current_user.id:
        raise AppException(
            code=1007,
            msg="The user doesn't have enough privileges",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return UserService.get_user(db, user_id)


@router.get("/", response_model=List[UserOut], summary="List all users")
async def list_users(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_active_superuser)
):
    """List all users. Requires superuser privileges."""
    return UserService.list_users(db)


@router.delete("/{user_id}", response_model=UserOut, summary="Delete a user")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser),
):
    """Delete a user. Requires superuser privileges."""
    return UserService.delete_user(db, user_id)
