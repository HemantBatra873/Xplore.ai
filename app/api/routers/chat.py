from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db, get_workspace_access
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm_service import generate_chat_reply, generate_chat_reply_stream
from app.services.workspace_service import WorkspaceAccess
from app.utils.rate_limit import RateLimiter

router = APIRouter()


# Chat endpoint: rate limit 20 requests per 60 seconds per client
@router.post(
    "/", summary="Chat with the assistant", dependencies=[Depends(RateLimiter(times=20, seconds=60))]
)
async def chat_with_ai(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    access: WorkspaceAccess = Depends(get_workspace_access),
):
    """
    Chat with the assistant. Supports tool calling and optional SSE streaming.
    Requires a valid JWT in the Authorization header.
    """
    workspace_id = access.workspace.id
    if request.stream:
        return StreamingResponse(
            generate_chat_reply_stream(
                message=request.message,
                db=db,
                current_user_id=current_user.id,
                workspace_id=workspace_id,
            ),
            media_type="text/event-stream",
        )
    reply = await generate_chat_reply(
        message=request.message,
        db=db,
        current_user_id=current_user.id,
        workspace_id=workspace_id,
    )
    return ChatResponse(reply=reply)
