from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import RETRY_AFTER_SECONDS
from app.core.errors.base import AppError


def register_exception_handlers(app):
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        body: dict = {"error_code": exc.error_code, "message": exc.message}
        if exc.detail is not None:
            body["detail"] = exc.detail
        if exc.status_code == 503:
            body["retry_after_seconds"] = RETRY_AFTER_SECONDS
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        validation_errors = []
        for error in exc.errors():
            loc = error.get("loc", ())
            field = ".".join(str(x) for x in loc if x != "body")
            validation_errors.append({
                "field": field or None,
                "issue": error.get("msg"),
                "value": error.get("input"),
            })
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "validation_errors": validation_errors,
            },
        )
