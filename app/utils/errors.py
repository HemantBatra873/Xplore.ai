from typing import Any, Optional

from fastapi import Request, status
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse


class AppException(Exception):
    """
    Application exception for business errors handled by global handlers.
    """

    def __init__(
        self,
        code: int,
        msg: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        data: Optional[Any] = None,
    ):
        self.code = code
        self.msg = msg
        self.status_code = status_code
        self.data = data


async def app_exception_handler(request: Request, exc: AppException):
    """
    Map AppException to unified JSON: {"code": ..., "msg": ..., "data": ...}
    """
    return JSONResponse(
        status_code=exc.status_code, content={"code": exc.code, "msg": exc.msg, "data": exc.data}
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Map HTTPException to the same JSON shape (401/403 from OAuth2, etc.).
    """
    code_map = {
        401: 1008,
        403: 1009,
        404: 1001,
        429: 1029,
    }
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": code_map.get(exc.status_code, exc.status_code),
            "msg": str(exc.detail),
            "data": None,
        },
    )
