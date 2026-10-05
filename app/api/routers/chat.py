from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm_service import generate_chat_reply, generate_chat_reply_stream
from app.utils.rate_limit import RateLimiter

router = APIRouter()


# Chat endpoint: rate limit 20 requests per 60 seconds per client
@router.post(
    "/", summary="Chat with the assistant", dependencies=[Depends(RateLimiter(times=20, seconds=60))]
)
async def chat_with_ai(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # Only signed-in users can chat by default
):
    """
    Chat with the assistant. Supports tool calling and optional SSE streaming.
    Requires a valid JWT in the Authorization header.
    """
    if request.stream:
        # Streaming response
        return StreamingResponse(
            generate_chat_reply_stream(
                message=request.message, db=db, current_user_id=current_user.id
            ),
            media_type="text/event-stream",
        )
    else:
        # Blocking response
        reply = await generate_chat_reply(
            message=request.message, db=db, current_user_id=current_user.id
        )
        return ChatResponse(reply=reply)
