import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ContextVar for the current request_id
request_id_context_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that assigns a unique request ID per HTTP request.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate UUID request_id
        request_id = str(uuid.uuid4())

        # Store in context var
        token = request_id_context_var.set(request_id)

        try:
            # Expose on request.state for route handlers
            request.state.request_id = request_id

            # Continue pipeline
            response = await call_next(request)

            # Echo X-Request-ID on the response
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            # Reset context var
            request_id_context_var.reset(token)
