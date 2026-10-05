from typing import Optional

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.workspace import Workspace
from app.schemas.knowledge import KnowledgeBaseCreate, KnowledgeBaseUpdate
from app.services.workspace_service import WorkspaceAccess
from app.utils.errors import AppException

DEFAULT_KNOWLEDGE_BASE_NAME = "General"
DEFAULT_KNOWLEDGE_BASE_DESCRIPTION = "Default knowledge base for this workspace"


class KnowledgeBaseService:
    @classmethod
    def create_default_for_workspace(
        cls,
        db: Session,
        *,
        workspace: Workspace,
        created_by_id: Optional[int] = None,
        commit: bool = True,
    ) -> KnowledgeBase:
        existing = db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.workspace_id == workspace.id,
                KnowledgeBase.name == DEFAULT_KNOWLEDGE_BASE_NAME,
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        kb = KnowledgeBase(
            workspace_id=workspace.id,
            name=DEFAULT_KNOWLEDGE_BASE_NAME,
            description=DEFAULT_KNOWLEDGE_BASE_DESCRIPTION,
            created_by_id=created_by_id or workspace.created_by_id,
        )
        db.add(kb)
        if commit:
            db.commit()
            db.refresh(kb)
        else:
            db.flush()
        return kb

    @classmethod
    def ensure_default_for_workspace(
        cls, db: Session, *, workspace: Workspace, created_by_id: Optional[int] = None
    ) -> KnowledgeBase:
        return cls.create_default_for_workspace(
            db, workspace=workspace, created_by_id=created_by_id, commit=True
        )

    @classmethod
    def get_for_workspace(
        cls, db: Session, *, knowledge_base_id: int, workspace_id: int
    ) -> KnowledgeBase:
        kb = db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == knowledge_base_id,
                KnowledgeBase.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()
        if kb is None:
            raise AppException(
                code=10404,
                msg="Knowledge base not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return kb

    @classmethod
    def list_for_workspace(cls, db: Session, *, workspace_id: int) -> list[KnowledgeBase]:
        return list(
            db.execute(
                select(KnowledgeBase)
                .where(KnowledgeBase.workspace_id == workspace_id)
                .order_by(KnowledgeBase.created_at.asc())
            )
            .scalars()
            .all()
        )

    @classmethod
    def document_count(cls, db: Session, *, knowledge_base_id: int) -> int:
        return int(
            db.scalar(
                select(func.count(Document.id)).where(
                    Document.knowledge_base_id == knowledge_base_id
                )
            )
            or 0
        )

    @classmethod
    def create(
        cls,
        db: Session,
        *,
        access: WorkspaceAccess,
        payload: KnowledgeBaseCreate,
    ) -> KnowledgeBase:
        access.require_permission("knowledge:write")
        name = payload.name.strip()
        existing = db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.workspace_id == access.workspace.id,
                KnowledgeBase.name == name,
            )
        ).scalar_one_or_none()
        if existing:
            raise AppException(
                code=10409,
                msg="A knowledge base with this name already exists in the workspace",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        kb = KnowledgeBase(
            workspace_id=access.workspace.id,
            name=name,
            description=payload.description,
            created_by_id=access.membership.user_id,
        )
        db.add(kb)
        db.commit()
        db.refresh(kb)
        return kb

    @classmethod
    def update(
        cls,
        db: Session,
        *,
        access: WorkspaceAccess,
        knowledge_base_id: int,
        payload: KnowledgeBaseUpdate,
    ) -> KnowledgeBase:
        access.require_permission("knowledge:write")
        kb = cls.get_for_workspace(
            db, knowledge_base_id=knowledge_base_id, workspace_id=access.workspace.id
        )
        data = payload.model_dump(exclude_unset=True)
        if "name" in data and data["name"] is not None:
            name = data["name"].strip()
            clash = db.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.workspace_id == access.workspace.id,
                    KnowledgeBase.name == name,
                    KnowledgeBase.id != kb.id,
                )
            ).scalar_one_or_none()
            if clash:
                raise AppException(
                    code=10409,
                    msg="A knowledge base with this name already exists in the workspace",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            kb.name = name
        if "description" in data:
            kb.description = data["description"]
        db.commit()
        db.refresh(kb)
        return kb

    @classmethod
    def delete(
        cls, db: Session, *, access: WorkspaceAccess, knowledge_base_id: int
    ) -> KnowledgeBase:
        access.require_permission("knowledge:admin")
        kb = cls.get_for_workspace(
            db, knowledge_base_id=knowledge_base_id, workspace_id=access.workspace.id
        )
        remaining = cls.list_for_workspace(db, workspace_id=access.workspace.id)
        if len(remaining) <= 1:
            raise AppException(
                code=10410,
                msg="A workspace must keep at least one knowledge base",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        db.delete(kb)
        db.commit()
        return kb
