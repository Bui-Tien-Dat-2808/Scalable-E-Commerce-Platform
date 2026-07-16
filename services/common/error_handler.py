from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel
from typing import Any, List, Optional
import logging

logger = logging.getLogger("shared-error-handler")


class ErrorResponseSchema(BaseModel):
    code: str
    message: str
    details: Optional[List[Any]] = None


class StandardErrorEnvelope(BaseModel):
    error: ErrorResponseSchema


def setup_error_handlers(app: FastAPI):
    """
    Đăng ký global exception handlers để chuẩn hóa cấu trúc lỗi cho FastAPI app.
    Cấu trúc trả về thống nhất: {"error": {"code": "...", "message": "...", "details": [...]}}
    """
    
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        code = "HTTP_ERROR"
        if exc.status_code == 401:
            code = "UNAUTHORIZED"
        elif exc.status_code == 403:
            code = "FORBIDDEN"
        elif exc.status_code == 404:
            code = "NOT_FOUND"
        elif exc.status_code == 409:
            code = "CONFLICT"
        elif exc.status_code == 400:
            code = "BAD_REQUEST"

        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code,
                    "message": message
                }
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        details = []
        for err in exc.errors():
            details.append({
                "field": " -> ".join(str(x) for x in err.get("loc", [])),
                "message": err.get("msg", ""),
                "type": err.get("type", "")
            })
        
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": details
                }
            }
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred on the server"
                }
            }
        )
