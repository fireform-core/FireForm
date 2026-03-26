from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from api.errors.base import AppError
from api.schemas.error import error_body

logger = logging.getLogger(__name__)

_HTTP_STATUS_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "UNPROCESSABLE_ENTITY",
    429: "TOO_MANY_REQUESTS",
    500: "INTERNAL_SERVER_ERROR",
    502: "BAD_GATEWAY",
    503: "SERVICE_UNAVAILABLE",
}


def _normalize_http_detail(detail: Any) -> tuple[str, Any | None]:
    if detail is None:
        return "Request failed", None
    if isinstance(detail, str):
        return detail, None
    if isinstance(detail, (list, dict)):
        return "Request failed", detail
    return str(detail), None


def _code_for_http_status(status: int) -> str:
    return _HTTP_STATUS_CODES.get(status, "HTTP_ERROR")


def register_exception_handlers(app) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        payload = error_body(
            status_code=422,
            code="VALIDATION_ERROR",
            message="Request validation failed",
            details=exc.errors(),
        )
        return JSONResponse(status_code=422, content=payload)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        msg, details = _normalize_http_detail(exc.detail)
        code = _code_for_http_status(exc.status_code)
        payload = error_body(
            status_code=exc.status_code,
            code=code,
            message=msg,
            details=details,
        )
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        payload = error_body(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        payload = error_body(
            status_code=500,
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            details=None,
        )
        return JSONResponse(status_code=500, content=payload)
