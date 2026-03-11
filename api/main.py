import logging
import time
from fastapi import FastAPI, Request
from api.routes import templates, forms
from api.errors.handlers import register_exception_handlers

logger = logging.getLogger("fireform.api")

app = FastAPI(title="FireForm API", version="1.0.0")

register_exception_handlers(app)

app.include_router(templates.router)
app.include_router(forms.router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    logger.info(
        "%s %s -> %s (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}