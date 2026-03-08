from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import templates, forms
from api.errors.handlers import register_exception_handlers

app = FastAPI(
    title="FireForm API",
    description="Report once, file everywhere.",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(templates.router)
app.include_router(forms.router)