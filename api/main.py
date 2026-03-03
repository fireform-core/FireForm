from fastapi import FastAPI
from api.routes import templates, forms, batch
from api.errors.handlers import register_exception_handlers

app = FastAPI(
    title="FireForm",
    description="Report once, file everywhere — multi-agency incident form filling.",
    version="0.2.0",
)

register_exception_handlers(app)

app.include_router(templates.router)
app.include_router(forms.router)
app.include_router(batch.router)