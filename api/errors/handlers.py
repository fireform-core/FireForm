"""
Global exception handlers for the FireForm API.

Ensures every error response returns a uniform JSON envelope matching
the ErrorResponse schema from api.schemas.common, regardless of whether
the error is a validation failure, a known application error, an HTTP
exception, or an unexpected crash.

Security: unhandled exceptions are logged server-side but never exposed
to the client.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.errors.base import AppError

logger = logging.getLogger("fireform")


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all global exception handlers to the FastAPI app."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        """Handle known application-level errors raised with AppError."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": "APPLICATION_ERROR",
                    "message": exc.message,
                },
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """
        Handle FastAPI/Starlette HTTPExceptions.

        templates.py raises HTTPException while forms.py raises AppError.
        This ensures both produce the same response shape for the frontend.
        """
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": "HTTP_ERROR",
                    "message": str(exc.detail),
                },
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """
        Handle Pydantic request validation failures.

        Extracts the first validation error and returns a human-readable
        message instead of dumping the raw Pydantic error array.
        """
        first = exc.errors()[0] if exc.errors() else {}
        field = " -> ".join(str(loc) for loc in first.get("loc", []))
        message = first.get("msg", "Validation failed")
        detail = f"{field}: {message}" if field else message

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": detail,
                },
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """
        Catch-all for unexpected exceptions.

        Logs the full traceback server-side for debugging but returns
        only a generic message to the client. This prevents leaking
        internal file paths, stack frames, and application state.
        """
        logger.exception(
            "Unhandled error on %s %s: %s",
            request.method,
            request.url.path,
            str(exc),
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Internal server error",
                },
            },
        )