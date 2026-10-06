"""Compatibility chat endpoint — thin wrapper over Conversations + AIOrchestrator."""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db, get_workspace_access
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.conversation import ConversationCreate
from app.services.ai_orchestrator import AIOrchestrator
from app.services.conversation_service import ConversationService
from app.services.workspace_service import WorkspaceAccess
from app.utils.rate_limit import RateLimiter

router = APIRouter()


@router.post(
    "/",
    summary="Chat with the assistant",
    dependencies=[Depends(RateLimiter(times=20, seconds=60))],
)
async def chat_with_ai(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    """
    Compatibility endpoint. Creates an ephemeral-titled conversation and sends one message
    through the unified AI orchestrator (same path as /conversations).
    Prefer /api/v1/conversations for persistent multi-turn chat.
    """
    access.require_permission("conversations:write")
    conversation = ConversationService.create(
        db,
        access=access,
        payload=ConversationCreate(title="New conversation", use_knowledge=False),
        created_by_id=current_user.id,
    )
    orchestrator = AIOrchestrator(db)

    if request.stream:
        return StreamingResponse(
            orchestrator.stream_message(
                access=access,
                user=current_user,
                conversation_id=conversation.id,
                content=request.message,
            ),
            media_type="text/event-stream",
        )

    result = await orchestrator.send_message(
        access=access,
        user=current_user,
        conversation_id=conversation.id,
        content=request.message,
    )
    return ChatResponse(reply=result.assistant_message.content)
