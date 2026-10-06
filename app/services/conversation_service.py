from datetime import datetime, timezone
from typing import Optional

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.conversation import Conversation, Message
from app.models.knowledge_base import KnowledgeBase
from app.schemas.conversation import ConversationCreate, ConversationUpdate
from app.services.workspace_service import WorkspaceAccess
from app.utils.errors import AppException


def parse_kb_ids(raw: Optional[str]) -> list[int]:
    if not raw or not raw.strip():
        return []
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids


def serialize_kb_ids(ids: Optional[list[int]]) -> Optional[str]:
    if not ids:
        return None
    cleaned = sorted({int(i) for i in ids if i is not None})
    return ",".join(str(i) for i in cleaned) if cleaned else None


class ConversationService:
    @classmethod
    def _validate_knowledge_bases(
        cls, db: Session, *, workspace_id: int, knowledge_base_ids: Optional[list[int]]
    ) -> None:
        if not knowledge_base_ids:
            return
        rows = (
            db.execute(
                select(KnowledgeBase.id).where(
                    KnowledgeBase.workspace_id == workspace_id,
                    KnowledgeBase.id.in_(knowledge_base_ids),
                )
            )
            .scalars()
            .all()
        )
        found = set(rows)
        missing = [kb_id for kb_id in knowledge_base_ids if kb_id not in found]
        if missing:
            raise AppException(
                code=10404,
                msg="One or more knowledge bases were not found in this workspace",
                status_code=status.HTTP_404_NOT_FOUND,
            )

    @classmethod
    def get_for_workspace(
        cls, db: Session, *, conversation_id: int, workspace_id: int
    ) -> Conversation:
        conversation = db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()
        if conversation is None:
            raise AppException(
                code=10404,
                msg="Conversation not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return conversation

    @classmethod
    def get_with_messages(
        cls, db: Session, *, conversation_id: int, workspace_id: int
    ) -> Conversation:
        conversation = db.execute(
            select(Conversation)
            .options(selectinload(Conversation.messages).selectinload(Message.citations))
            .where(
                Conversation.id == conversation_id,
                Conversation.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()
        if conversation is None:
            raise AppException(
                code=10404,
                msg="Conversation not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return conversation

    @classmethod
    def list_for_workspace(
        cls, db: Session, *, workspace_id: int, created_by_id: Optional[int] = None
    ) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.workspace_id == workspace_id)
            .order_by(Conversation.updated_at.desc())
        )
        if created_by_id is not None:
            stmt = stmt.where(Conversation.created_by_id == created_by_id)
        return list(db.execute(stmt).scalars().all())

    @classmethod
    def _validate_agent(cls, db: Session, *, workspace_id: int, agent_id: Optional[int]) -> None:
        if agent_id is None:
            return
        from app.services.agent_service import AgentService

        AgentService.get_for_workspace(db, agent_id=agent_id, workspace_id=workspace_id)

    @classmethod
    def create(
        cls,
        db: Session,
        *,
        access: WorkspaceAccess,
        payload: ConversationCreate,
        created_by_id: int,
    ) -> Conversation:
        access.require_permission("conversations:write")
        cls._validate_knowledge_bases(
            db,
            workspace_id=access.workspace.id,
            knowledge_base_ids=payload.knowledge_base_ids,
        )
        cls._validate_agent(db, workspace_id=access.workspace.id, agent_id=payload.agent_id)
        title = (payload.title or "New conversation").strip() or "New conversation"
        conversation = Conversation(
            workspace_id=access.workspace.id,
            created_by_id=created_by_id,
            title=title[:200],
            use_knowledge=bool(payload.use_knowledge),
            knowledge_base_ids=serialize_kb_ids(payload.knowledge_base_ids),
            agent_id=payload.agent_id,
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation

    @classmethod
    def update(
        cls,
        db: Session,
        *,
        access: WorkspaceAccess,
        conversation_id: int,
        payload: ConversationUpdate,
    ) -> Conversation:
        access.require_permission("conversations:write")
        conversation = cls.get_for_workspace(
            db, conversation_id=conversation_id, workspace_id=access.workspace.id
        )
        data = payload.model_dump(exclude_unset=True)
        if "title" in data and data["title"] is not None:
            conversation.title = data["title"].strip()[:200]
        if "use_knowledge" in data and data["use_knowledge"] is not None:
            conversation.use_knowledge = bool(data["use_knowledge"])
        if "knowledge_base_ids" in data:
            cls._validate_knowledge_bases(
                db,
                workspace_id=access.workspace.id,
                knowledge_base_ids=data["knowledge_base_ids"],
            )
            conversation.knowledge_base_ids = serialize_kb_ids(data["knowledge_base_ids"])
        if "agent_id" in data:
            cls._validate_agent(db, workspace_id=access.workspace.id, agent_id=data["agent_id"])
            conversation.agent_id = data["agent_id"]
        conversation.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(conversation)
        return conversation

    @classmethod
    def delete(cls, db: Session, *, access: WorkspaceAccess, conversation_id: int) -> Conversation:
        access.require_permission("conversations:write")
        conversation = cls.get_for_workspace(
            db, conversation_id=conversation_id, workspace_id=access.workspace.id
        )
        db.delete(conversation)
        db.commit()
        return conversation

    @classmethod
    def list_messages(
        cls, db: Session, *, access: WorkspaceAccess, conversation_id: int
    ) -> list[Message]:
        access.require_permission("conversations:read")
        conversation = cls.get_with_messages(
            db, conversation_id=conversation_id, workspace_id=access.workspace.id
        )
        return list(conversation.messages)

    @classmethod
    def touch(cls, db: Session, conversation: Conversation) -> None:
        conversation.updated_at = datetime.now(timezone.utc)
        db.add(conversation)
