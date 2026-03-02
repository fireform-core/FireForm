from fastapi import FastAPI
from api.routes import templates, forms
from api.errors.handlers import register_exception_handlers

app = FastAPI(
    title="FireForm API",
    description="Report once, file everywhere — AI-powered form filling for first responders.",
    version="1.0.0",
)

register_exception_handlers(app)

app.include_router(templates.router)
app.include_router(forms.router)


@app.get("/health", tags=["health"])
def health_check():
    """Liveness probe — confirms the API is running."""
    return {"status": "ok", "service": "fireform"}