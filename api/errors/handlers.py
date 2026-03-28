from fastapi import Request
from fastapi.responses import JSONResponse
from api.errors.base import AppError, ValidationError
from src.filler import FormValidationError


def register_exception_handlers(app):
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message},
        )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": exc.message,
                "validation_errors": exc.errors
            },
        )

    @app.exception_handler(FormValidationError)
    async def form_validation_error_handler(request: Request, exc: FormValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": "Incident data validation failed",
                "validation_errors": exc.errors,
                "extracted_data": exc.data
            },
        )