from datetime import timedelta

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.auth import SetupRequest, SetupStatus, Token
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.utils.errors import AppException

router = APIRouter()


@router.get("/setup/status", response_model=SetupStatus, summary="Check system setup status")
async def get_setup_status(db: Session = Depends(get_db)):
    """Return whether the system has been initialized (at least one user exists)."""
    user_count = db.execute(select(func.count(User.id))).scalar()
    return SetupStatus(
        initialized=user_count > 0,
        llm_mock=settings.LLM_MOCK,
        llm_provider=settings.LLM_PROVIDER,
    )


@router.post("/setup", response_model=Token, summary="Initial setup: create an administrator and sign in")
async def initial_setup(
    setup_in: SetupRequest,
    db: Session = Depends(get_db),
):
    """
    Create the first administrator user and return a JWT token.
    Available only when the system has no users yet.
    """
    user_count = db.execute(select(func.count(User.id))).scalar()
    if user_count > 0:
        raise AppException(
            code=1010, msg="System already initialized", status_code=status.HTTP_400_BAD_REQUEST
        )

    user_in = type(
        "UserCreate",
        (),
        {
            "username": setup_in.username,
            "email": setup_in.email,
            "password": setup_in.password,
            "full_name": setup_in.full_name or setup_in.username,
        },
    )()

    user = UserService.create_user(db, user_in)

    # First registered user becomes superuser
    user.is_superuser = True
    db.commit()
    db.refresh(user)

    # If an LLM API key was provided, persist it on the user
    if setup_in.llm_api_key:
        from app.schemas.user import UserLLMConfigUpdate

        UserService.update_llm_config(
            db,
            user.id,
            UserLLMConfigUpdate(
                llm_provider=setup_in.llm_provider or settings.LLM_PROVIDER,
                llm_base_url=setup_in.llm_base_url or settings.LLM_BASE_URL,
                llm_model_name=setup_in.llm_model_name or settings.LLM_MODEL_NAME,
                llm_api_key=setup_in.llm_api_key,
            ),
        )

    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=Token, summary="Sign in and get a token")
async def login_access_token(
    db: Session = Depends(get_db),
    # OAuth2PasswordRequestForm expects x-www-form-urlencoded (username and password)
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """
    OAuth2-compatible token login. Clients send email in the username field
    and receive a JWT access token on success.
    """
    user = AuthService.authenticate_user(db, email=form_data.username, password=form_data.password)

    if not user:
        raise AppException(
            code=1005, msg="Incorrect email or password", status_code=status.HTTP_401_UNAUTHORIZED
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    # JWT "sub" (subject) holds the user identifier
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}
