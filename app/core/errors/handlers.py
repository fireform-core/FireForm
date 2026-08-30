import json

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import RETRY_AFTER_SECONDS
from app.core.errors.base import AppError, ValidationAppError


def _jsonable(value):
    """Return value untouched if JSON-serializable, else a string form.

    FastAPI puts the offending input on each validation error. When a JSON-body
    endpoint is called with the wrong content-type, that input is the raw
    request body as bytes, which JSONResponse cannot encode. Coerce anything
    non-serializable so the 422 renders instead of turning into a 500.
    """
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
        return str(value)


def register_exception_handlers(app):
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        body: dict = {"error_code": exc.error_code, "message": exc.message}
        if exc.detail is not None:
            body["detail"] = exc.detail
        if exc.status_code == 503:
            body["retry_after_seconds"] = RETRY_AFTER_SECONDS
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(ValidationAppError)
    async def validation_app_error_handler(request: Request, exc: ValidationAppError):
        body: dict = {"error_code": exc.error_code, "message": exc.message}
        if exc.detail is not None:
            body["detail"] = exc.detail
        if exc.validation_errors:
            body["validation_errors"] = [
                {**error, "value": _jsonable(error.get("value"))}
                for error in exc.validation_errors
            ]
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
                "value": _jsonable(error.get("input")),
            })
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "validation_errors": validation_errors,
            },
        )
