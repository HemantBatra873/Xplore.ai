from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db, get_workspace_access
from app.models.conversation import Message
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
    ConversationUpdate,
    MessageCitationOut,
    MessageOut,
    SendMessageRequest,
    SendMessageResponse,
)
from app.schemas.knowledge import CitationSource
from app.services.ai_orchestrator import AIOrchestrator
from app.services.conversation_service import ConversationService, parse_kb_ids
from app.services.workspace_service import WorkspaceAccess

router = APIRouter()


def _current_user(db: Session, access: WorkspaceAccess) -> User:
    user = db.get(User, access.membership.user_id)
    if user is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="User not found")
    return user


def _conversation_out(conversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        workspace_id=conversation.workspace_id,
        created_by_id=conversation.created_by_id,
        title=conversation.title,
        use_knowledge=conversation.use_knowledge,
        knowledge_base_ids=parse_kb_ids(conversation.knowledge_base_ids),
        agent_id=conversation.agent_id,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _message_out(message: Message) -> MessageOut:
    import json

    tool_calls = []
    if message.tool_calls_json:
        try:
            tool_calls = json.loads(message.tool_calls_json)
        except json.JSONDecodeError:
            tool_calls = []
    citations = [
        MessageCitationOut(
            id=c.id,
            chunk_id=c.chunk_id or 0,
            document_id=c.document_id or 0,
            knowledge_base_id=c.knowledge_base_id or 0,
            knowledge_base_name=c.knowledge_base_name,
            filename=c.filename,
            chunk_index=c.chunk_index,
            excerpt=c.excerpt,
            score=c.score,
        )
        for c in (message.citations or [])
    ]
    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        status=message.status,
        error_message=message.error_message,
        tool_calls=tool_calls,
        citations=citations,
        created_at=message.created_at,
    )


@router.get("/", response_model=list[ConversationOut], summary="List conversations")
async def list_conversations(
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("conversations:read")
    items = ConversationService.list_for_workspace(db, workspace_id=access.workspace.id)
    return [_conversation_out(c) for c in items]


@router.post(
    "/",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a conversation",
)
async def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    user = _current_user(db, access)
    conversation = ConversationService.create(
        db, access=access, payload=payload, created_by_id=user.id
    )
    return _conversation_out(conversation)


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetailOut,
    summary="Get a conversation with messages",
)
async def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    access.require_permission("conversations:read")
    conversation = ConversationService.get_with_messages(
        db, conversation_id=conversation_id, workspace_id=access.workspace.id
    )
    base = _conversation_out(conversation)
    return ConversationDetailOut(
        **base.model_dump(),
        messages=[_message_out(m) for m in conversation.messages],
    )


@router.patch(
    "/{conversation_id}",
    response_model=ConversationOut,
    summary="Update a conversation",
)
async def update_conversation(
    conversation_id: int,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    conversation = ConversationService.update(
        db, access=access, conversation_id=conversation_id, payload=payload
    )
    return _conversation_out(conversation)


@router.delete("/{conversation_id}", summary="Delete a conversation")
async def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    conversation = ConversationService.delete(db, access=access, conversation_id=conversation_id)
    return JSONResponse(
        content={"message": "Conversation deleted", "conversation_id": conversation.id}
    )


@router.get(
    "/{conversation_id}/messages",
    response_model=list[MessageOut],
    summary="List messages",
)
async def list_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    messages = ConversationService.list_messages(db, access=access, conversation_id=conversation_id)
    return [_message_out(m) for m in messages]


@router.post(
    "/{conversation_id}/messages",
    response_model=SendMessageResponse,
    summary="Send a message (non-streaming)",
)
async def send_message(
    conversation_id: int,
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    user = _current_user(db, access)
    orchestrator = AIOrchestrator(db)
    result = await orchestrator.send_message(
        access=access,
        user=user,
        conversation_id=conversation_id,
        content=payload.content,
        use_knowledge=payload.use_knowledge,
        knowledge_base_ids=payload.knowledge_base_ids,
        agent_id=payload.agent_id,
        top_k=payload.top_k,
        enable_rerank=payload.enable_rerank,
        enable_hybrid=payload.enable_hybrid,
    )
    # Reload assistant with citations
    assistant = db.execute(
        select(Message)
        .options(selectinload(Message.citations))
        .where(Message.id == result.assistant_message.id)
    ).scalar_one()
    sources = [
        CitationSource(
            chunk_id=c.chunk_id or 0,
            document_id=c.document_id or 0,
            knowledge_base_id=c.knowledge_base_id or 0,
            knowledge_base_name=c.knowledge_base_name,
            filename=c.filename,
            chunk_index=c.chunk_index,
            excerpt=c.excerpt,
            score=c.score,
        )
        for c in assistant.citations
    ]
    return SendMessageResponse(
        user_message=_message_out(result.user_message),
        assistant_message=_message_out(assistant),
        sources=sources,
    )


@router.post(
    "/{conversation_id}/messages/stream",
    summary="Send a message (SSE streaming)",
)
async def send_message_stream(
    conversation_id: int,
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    user = _current_user(db, access)
    orchestrator = AIOrchestrator(db)

    async def event_gen():
        async for line in orchestrator.stream_message(
            access=access,
            user=user,
            conversation_id=conversation_id,
            content=payload.content,
            use_knowledge=payload.use_knowledge,
            knowledge_base_ids=payload.knowledge_base_ids,
            agent_id=payload.agent_id,
            top_k=payload.top_k,
            enable_rerank=payload.enable_rerank,
            enable_hybrid=payload.enable_hybrid,
        ):
            yield line

    return StreamingResponse(event_gen(), media_type="text/event-stream")
