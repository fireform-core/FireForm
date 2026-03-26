from fastapi import FastAPI

from api.errors.handlers import register_exception_handlers
from api.routes import forms, templates

app = FastAPI()
register_exception_handlers(app)

app.include_router(templates.router)
app.include_router(forms.router)