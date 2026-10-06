from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_workspace_access
from app.models.user import User
from app.schemas.agent import (
    AgentCreate,
    AgentKnowledgeUpdate,
    AgentOut,
    AgentToolsUpdate,
    AgentUpdate,
    ToolInfoOut,
)
from app.services.agent_service import AgentService
from app.services.tool_registry import ToolRegistry
from app.services.workspace_service import WorkspaceAccess

router = APIRouter()


def _current_user(db: Session, access: WorkspaceAccess) -> User:
    user = db.get(User, access.membership.user_id)
    if user is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="User not found")
    return user


def _agent_out(agent) -> AgentOut:
    return AgentOut(
        id=agent.id,
        workspace_id=agent.workspace_id,
        created_by_id=agent.created_by_id,
        name=agent.name,
        description=agent.description,
        system_prompt=agent.system_prompt,
        provider=agent.provider,
        model_name=agent.model_name,
        is_enabled=agent.is_enabled,
        knowledge_base_ids=AgentService.knowledge_base_ids(agent),
        enabled_tools=AgentService.enabled_tool_names(agent),
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


@router.get(
    "/tools",
    response_model=list[ToolInfoOut],
    summary="List available internal and integration tools",
)
async def list_tools(
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("tools:use")
    return [
        ToolInfoOut(
            name=d.name,
            description=d.description,
            input_schema=d.input_schema,
            requires_workspace=d.requires_workspace,
            requires_user=d.requires_user,
            enabled=d.enabled,
            source=d.source,
            integration_id=d.integration_id,
            integration_name=d.integration_name,
        )
        for d in ToolRegistry.list_definitions(
            db=db, workspace_id=access.workspace.id
        )
    ]


@router.get("/", response_model=list[AgentOut], summary="List agents")
async def list_agents(
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("agents:read")
    agents = AgentService.list_for_workspace(db, workspace_id=access.workspace.id)
    return [_agent_out(a) for a in agents]


@router.post(
    "/",
    response_model=AgentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an agent",
)
async def create_agent(
    payload: AgentCreate,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    user = _current_user(db, access)
    agent = AgentService.create(
        db, access=access, payload=payload, created_by_id=user.id
    )
    return _agent_out(agent)


@router.get("/{agent_id}", response_model=AgentOut, summary="Get an agent")
async def get_agent(
    agent_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("agents:read")
    agent = AgentService.get_for_workspace(
        db, agent_id=agent_id, workspace_id=access.workspace.id
    )
    return _agent_out(agent)


@router.put("/{agent_id}", response_model=AgentOut, summary="Update an agent")
@router.patch("/{agent_id}", response_model=AgentOut, summary="Update an agent")
async def update_agent(
    agent_id: int,
    payload: AgentUpdate,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    agent = AgentService.update(db, access=access, agent_id=agent_id, payload=payload)
    return _agent_out(agent)


@router.delete("/{agent_id}", summary="Delete an agent")
async def delete_agent(
    agent_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    agent = AgentService.delete(db, access=access, agent_id=agent_id)
    return JSONResponse(content={"message": "Agent deleted", "agent_id": agent.id})


@router.put(
    "/{agent_id}/knowledge-bases",
    response_model=AgentOut,
    summary="Replace agent knowledge bases",
)
async def set_agent_knowledge(
    agent_id: int,
    payload: AgentKnowledgeUpdate,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    agent = AgentService.set_knowledge_bases(
        db,
        access=access,
        agent_id=agent_id,
        knowledge_base_ids=payload.knowledge_base_ids,
    )
    return _agent_out(agent)


@router.put(
    "/{agent_id}/tools",
    response_model=AgentOut,
    summary="Replace agent enabled tools",
)
async def set_agent_tools(
    agent_id: int,
    payload: AgentToolsUpdate,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    agent = AgentService.set_tools(
        db, access=access, agent_id=agent_id, enabled_tools=payload.enabled_tools
    )
    return _agent_out(agent)
