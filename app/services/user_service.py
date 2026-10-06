from fastapi import status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from app.schemas.user import PasswordUpdate, UserCreate, UserLLMConfigUpdate
from app.services.workspace_service import WorkspaceService
from app.utils.encryption import encrypt_api_key
from app.utils.errors import AppException


class UserService:
    """
    User service layer (database-backed).
    """

    @classmethod
    def create_user(cls, db: Session, user_in: UserCreate) -> User:
        logger.info(f"Attempting to create user with email: {user_in.email}")

        # 1. Ensure email is not already registered
        # SQLAlchemy 2.0 select() style query
        existing_user = db.execute(
            select(User).where(User.email == user_in.email)
        ).scalar_one_or_none()

        if existing_user:
            logger.warning(f"Registration failed: Email already registered ({user_in.email})")
            raise AppException(
                code=1001, msg="Email already registered", status_code=status.HTTP_400_BAD_REQUEST
            )

        # 2. Map request schema to ORM model and hash the password
        db_user = User(
            username=user_in.username,
            email=user_in.email,
            full_name=user_in.full_name,
            hashed_password=get_password_hash(user_in.password),
            is_active=True,
        )

        # 3. Persist and commit
        db.add(db_user)
        db.commit()
        db.refresh(db_user)  # Refresh for DB-generated id

        WorkspaceService.create_personal_workspace(db, db_user)

        logger.info(f"User created successfully. ID: {db_user.id}")
        return db_user

    @classmethod
    def get_user(cls, db: Session, user_id: int) -> User:
        logger.info(f"Fetching user with ID: {user_id}")

        # db.get() loads by primary key
        user = db.get(User, user_id)
        if not user:
            logger.warning(f"User fetch failed: ID {user_id} not found")
            raise AppException(
                code=1002, msg="User not found", status_code=status.HTTP_404_NOT_FOUND
            )
        return user

    @classmethod
    def list_users(cls, db: Session) -> list[User]:
        logger.info("Fetching all users")
        # Run query and return all rows
        return list(db.scalars(select(User)).all())

    @classmethod
    def delete_user(cls, db: Session, user_id: int) -> User:
        logger.info(f"Attempting to delete user with ID: {user_id}")
        user = db.get(User, user_id)
        if not user:
            logger.warning(f"User delete failed: ID {user_id} not found")
            raise AppException(
                code=1002, msg="User not found", status_code=status.HTTP_404_NOT_FOUND
            )
        # Break workspace ownership / membership links before ORM delete so SQLite
        # and Postgres both succeed (workspaces survive with null created_by_id).
        user.default_workspace_id = None
        db.flush()
        db.execute(
            update(Workspace).where(Workspace.created_by_id == user_id).values(created_by_id=None)
        )
        db.execute(delete(WorkspaceMembership).where(WorkspaceMembership.user_id == user_id))
        db.delete(user)
        db.commit()
        logger.info(f"User deleted successfully. ID: {user_id}")
        return user

    @classmethod
    def update_llm_config(cls, db: Session, user_id: int, config_in: UserLLMConfigUpdate) -> User:
        logger.info(f"Attempting to update LLM config for user ID: {user_id}")
        user = db.get(User, user_id)
        if not user:
            raise AppException(
                code=1002, msg="User not found", status_code=status.HTTP_404_NOT_FOUND
            )

        update_data = {}
        if config_in.llm_provider is not None:
            update_data["llm_provider"] = (
                config_in.llm_provider if config_in.llm_provider.strip() else None
            )
        if config_in.llm_base_url is not None:
            update_data["llm_base_url"] = (
                config_in.llm_base_url if config_in.llm_base_url.strip() else None
            )
        if config_in.llm_model_name is not None:
            update_data["llm_model_name"] = (
                config_in.llm_model_name if config_in.llm_model_name.strip() else None
            )
        if config_in.llm_api_key is not None:
            if config_in.llm_api_key.strip() == "":
                update_data["llm_api_key_encrypted"] = None
            else:
                update_data["llm_api_key_encrypted"] = encrypt_api_key(config_in.llm_api_key)

        for field, value in update_data.items():
            setattr(user, field, value)

        db.commit()
        db.refresh(user)
        return user

    @classmethod
    def change_password(cls, db: Session, user_id: int, password_in: PasswordUpdate) -> User:
        logger.info(f"Attempting to change password for user ID: {user_id}")
        user = db.get(User, user_id)
        if not user:
            raise AppException(
                code=1002, msg="User not found", status_code=status.HTTP_404_NOT_FOUND
            )

        if not verify_password(password_in.old_password, user.hashed_password):
            raise AppException(
                code=1008,
                msg="Old password is incorrect",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        user.hashed_password = get_password_hash(password_in.new_password)
        db.commit()
        db.refresh(user)
        logger.info(f"Password changed successfully for user ID: {user_id}")
        return user
