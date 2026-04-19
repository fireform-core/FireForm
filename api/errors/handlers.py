from fastapi import Request
from fastapi.responses import JSONResponse
from api.errors.base import AppError

def register_exception_handlers(app):
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message},
        )