"""核心基础设施模块：exceptions。"""

from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.log_config import get_logger

logger = get_logger(__name__)


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: Any = None
    request_id: str | None = None


class AppError(Exception):
    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Any = None,
    ):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(
        self,
        message: str = "Resource not found",
        details: Any = None,
        error_code: str = "NOT_FOUND",
    ):
        super().__init__(error_code=error_code, message=message, status_code=status.HTTP_404_NOT_FOUND, details=details)


class ValidationError(AppError):
    def __init__(
        self,
        message: str = "Validation error",
        details: Any = None,
        error_code: str = "VALIDATION_ERROR",
    ):
        super().__init__(
            error_code=error_code,
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class ServiceUnavailableError(AppError):
    def __init__(self, message: str = "Service unavailable", details: Any = None):
        super().__init__(
            error_code="SERVICE_UNAVAILABLE",
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
        )


class PermissionDeniedError(AppError):
    def __init__(self, message: str = "Permission denied", details: Any = None):
        super().__init__(
            error_code="PERMISSION_DENIED",
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class ConflictError(AppError):
    def __init__(
        self,
        message: str = "Resource conflict",
        details: Any = None,
        error_code: str = "CONFLICT",
    ):
        super().__init__(
            error_code=error_code,
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, Exception):
        return str(value)
    return value


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID", None)
    logger.error(
        "Application exception",
        error_code=exc.error_code,
        message=exc.message,
        status_code=exc.status_code,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            details=_to_jsonable(exc.details),
            request_id=request_id,
        ).model_dump(),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID", None)
    logger.error("Validation error", errors=exc.errors())

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error_code="VALIDATION_ERROR",
            message="Request validation failed",
            details=_to_jsonable(exc.errors()),
            request_id=request_id,
        ).model_dump(),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID", None)
    logger.exception("Unexpected error", error=str(exc))

    error_details = str(exc) if request.app.debug else None
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error_code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            details=error_details,
            request_id=request_id,
        ).model_dump(),
    )
