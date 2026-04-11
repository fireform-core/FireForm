import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from api.errors.base import AppError
from api.schemas.common import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def register_exception_handlers(app):
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        logger.warning(
            "AppError on %s %s: [%d] %s",
            request.method,
            request.url.path,
            exc.status_code,
            exc.message,
        )
        payload = ErrorResponse(
            error=ErrorDetail(
                code=f"ERR_{exc.status_code}",
                message=exc.message,
            )
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=payload.model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception(
            "Unhandled exception on %s %s",
            request.method,
            request.url.path,
        )
        payload = ErrorResponse(
            error=ErrorDetail(
                code="ERR_500",
                message="An internal server error occurred.",
            )
        )
        return JSONResponse(
            status_code=500,
            content=payload.model_dump(),
        )