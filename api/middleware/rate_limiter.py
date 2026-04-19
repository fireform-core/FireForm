"""
Rate limiting middleware for the FireForm API.

Protects endpoints from abuse by limiting requests per client IP.
Uses slowapi which integrates with FastAPI's dependency injection.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


limiter = Limiter(key_func=get_remote_address)


def register_rate_limiter(app: FastAPI) -> None:
    """Register rate limiting middleware and error handler on the app."""
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Too many requests. Limit: {exc.detail}",
                },
            },
        )