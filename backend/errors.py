from fastapi import Request
from fastapi.responses import JSONResponse

from schemas.common import ErrorCode, ErrorResponse


class ApiError(Exception):
    def __init__(self, status: int, code: ErrorCode, message: str, details: dict | None = None):
        self.status, self.code, self.message, self.details = status, code, message, details


async def api_error_handler(_: Request, exc: ApiError):
    body = ErrorResponse(code=exc.code, message=exc.message, details=exc.details)
    return JSONResponse(status_code=exc.status, content=body.model_dump(mode="json"))
