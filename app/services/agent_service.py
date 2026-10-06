from datetime import datetime, timezone
from typing import Optional

from fastapi import status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.agent import Agent, AgentKnowledgeBase
from app.models.knowledge_base import KnowledgeBase
from app.schemas.agent import AgentCreate, AgentUpdate
from app.services.tool_registry import ToolRegistry, parse_tool_names, serialize_tool_names
from app.services.workspace_service import WorkspaceAccess
from app.utils.errors import AppException


class AgentService:
    @classmethod
    def get_for_workspace(
        cls, db: Session, *, agent_id: int, workspace_id: int
    ) -> Agent:
        agent = db.execute(
            select(Agent)
            .options(selectinload(Agent.knowledge_links))
            .where(Agent.id == agent_id, Agent.workspace_id == workspace_id)
        ).scalar_one_or_none()
        if agent is None:
            raise AppException(
                code=10404,
                msg="Agent not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return agent

    @classmethod
    def list_for_workspace(
        cls, db: Session, *, workspace_id: int, enabled_only: bool = False
    ) -> list[Agent]:
        stmt = (
            select(Agent)
            .options(selectinload(Agent.knowledge_links))
            .where(Agent.workspace_id == workspace_id)
            .order_by(Agent.created_at.asc())
        )
        if enabled_only:
            stmt = stmt.where(Agent.is_enabled.is_(True))
        return list(db.execute(stmt).scalars().all())

    @classmethod
    def _validate_kbs(
        cls, db: Session, *, workspace_id: int, knowledge_base_ids: list[int]
    ) -> None:
        if not knowledge_base_ids:
            return
        found = set(
            db.execute(
                select(KnowledgeBase.id).where(
                    KnowledgeBase.workspace_id == workspace_id,
                    KnowledgeBase.id.in_(knowledge_base_ids),
                )
            )
            .scalars()
            .all()
        )
        missing = [kb_id for kb_id in knowledge_base_ids if kb_id not in found]
        if missing:
            raise AppException(
                code=10404,
                msg="One or more knowledge bases were not found in this workspace",
                status_code=status.HTTP_404_NOT_FOUND,
            )

    @classmethod
    def _validate_tools(
        cls, db: Session, *, workspace_id: int, tool_names: list[str]
    ) -> set[str]:
        known = {
            d.name
            for d in ToolRegistry.list_definitions(db=db, workspace_id=workspace_id)
            if d.enabled
        }
        unknown = [n for n in tool_names if n not in known]
        if unknown:
            raise AppException(
                code=10422,
                msg=f"Unknown tools: {', '.join(unknown)}",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return known

    @classmethod
    def _set_knowledge_links(
        cls, db: Session, *, agent: Agent, knowledge_base_ids: list[int]
    ) -> None:
        db.execute(delete(AgentKnowledgeBase).where(AgentKnowledgeBase.agent_id == agent.id))
        for kb_id in sorted(set(knowledge_base_ids)):
            db.add(AgentKnowledgeBase(agent_id=agent.id, knowledge_base_id=kb_id))

    @classmethod
    def create(
        cls,
        db: Session,
        *,
        access: WorkspaceAccess,
        payload: AgentCreate,
        created_by_id: int,
    ) -> Agent:
        access.require_permission("agents:manage")
        name = payload.name.strip()
        existing = db.execute(
            select(Agent).where(
                Agent.workspace_id == access.workspace.id, Agent.name == name
            )
        ).scalar_one_or_none()
        if existing:
            raise AppException(
                code=10409,
                msg="An agent with this name already exists in the workspace",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        cls._validate_kbs(
            db, workspace_id=access.workspace.id, knowledge_base_ids=payload.knowledge_base_ids
        )
        known = cls._validate_tools(
            db, workspace_id=access.workspace.id, tool_names=payload.enabled_tools
        )

        agent = Agent(
            workspace_id=access.workspace.id,
            created_by_id=created_by_id,
            name=name,
            description=payload.description,
            system_prompt=payload.system_prompt.strip(),
            provider=payload.provider,
            model_name=payload.model_name,
            is_enabled=payload.is_enabled,
            enabled_tools=serialize_tool_names(payload.enabled_tools, known=known),
        )
        db.add(agent)
        db.flush()
        cls._set_knowledge_links(
            db, agent=agent, knowledge_base_ids=payload.knowledge_base_ids
        )
        db.commit()
        return cls.get_for_workspace(
            db, agent_id=agent.id, workspace_id=access.workspace.id
        )

    @classmethod
    def update(
        cls,
        db: Session,
        *,
        access: WorkspaceAccess,
        agent_id: int,
        payload: AgentUpdate,
    ) -> Agent:
        access.require_permission("agents:manage")
        agent = cls.get_for_workspace(
            db, agent_id=agent_id, workspace_id=access.workspace.id
        )
        data = payload.model_dump(exclude_unset=True)
        if "name" in data and data["name"] is not None:
            name = data["name"].strip()
            clash = db.execute(
                select(Agent).where(
                    Agent.workspace_id == access.workspace.id,
                    Agent.name == name,
                    Agent.id != agent.id,
                )
            ).scalar_one_or_none()
            if clash:
                raise AppException(
                    code=10409,
                    msg="An agent with this name already exists in the workspace",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            agent.name = name
        if "description" in data:
            agent.description = data["description"]
        if "system_prompt" in data and data["system_prompt"] is not None:
            agent.system_prompt = data["system_prompt"].strip()
        if "provider" in data:
            agent.provider = data["provider"]
        if "model_name" in data:
            agent.model_name = data["model_name"]
        if "is_enabled" in data and data["is_enabled"] is not None:
            agent.is_enabled = bool(data["is_enabled"])
        if "enabled_tools" in data and data["enabled_tools"] is not None:
            known = cls._validate_tools(
                db, workspace_id=access.workspace.id, tool_names=data["enabled_tools"]
            )
            agent.enabled_tools = serialize_tool_names(data["enabled_tools"], known=known)
        if "knowledge_base_ids" in data and data["knowledge_base_ids"] is not None:
            cls._validate_kbs(
                db,
                workspace_id=access.workspace.id,
                knowledge_base_ids=data["knowledge_base_ids"],
            )
            cls._set_knowledge_links(
                db, agent=agent, knowledge_base_ids=data["knowledge_base_ids"]
            )
        agent.updated_at = datetime.now(timezone.utc)
        db.commit()
        return cls.get_for_workspace(
            db, agent_id=agent.id, workspace_id=access.workspace.id
        )

    @classmethod
    def delete(cls, db: Session, *, access: WorkspaceAccess, agent_id: int) -> Agent:
        access.require_permission("agents:manage")
        agent = cls.get_for_workspace(
            db, agent_id=agent_id, workspace_id=access.workspace.id
        )
        db.delete(agent)
        db.commit()
        return agent

    @classmethod
    def set_knowledge_bases(
        cls,
        db: Session,
        *,
        access: WorkspaceAccess,
        agent_id: int,
        knowledge_base_ids: list[int],
    ) -> Agent:
        return cls.update(
            db,
            access=access,
            agent_id=agent_id,
            payload=AgentUpdate(knowledge_base_ids=knowledge_base_ids),
        )

    @classmethod
    def set_tools(
        cls,
        db: Session,
        *,
        access: WorkspaceAccess,
        agent_id: int,
        enabled_tools: list[str],
    ) -> Agent:
        return cls.update(
            db,
            access=access,
            agent_id=agent_id,
            payload=AgentUpdate(enabled_tools=enabled_tools),
        )

    @classmethod
    def knowledge_base_ids(cls, agent: Agent) -> list[int]:
        return sorted({link.knowledge_base_id for link in (agent.knowledge_links or [])})

    @classmethod
    def enabled_tool_names(cls, agent: Optional[Agent]) -> list[str]:
        if agent is None:
            return []
        return parse_tool_names(agent.enabled_tools)
