import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import FastAPI
from api.routes import templates, forms
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI()

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(RequestIDMiddleware)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "type": "HTTPException",
                "message": exc.detail,
                "details": {}
            }
        },
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    formatted_errors = []

    for err in exc.errors():
        loc = err.get("loc", [])
        field = loc[-1] if loc else "unknown"  
        issue = err.get("msg", "Invalid value")
        expected = err.get("type", "")

        formatted_errors.append({
            "field": field,
            "issue": issue,
            "expected": expected
        })

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "type": "ValidationError",
                "message": "Invalid request data",
                "details": formatted_errors,
            }
        },
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "type": "InternalServerError",
                "message": str(exc),
                "details": {}
            }
        },
    )


app.include_router(templates.router)
app.include_router(forms.router)