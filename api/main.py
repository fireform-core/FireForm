from fastapi import FastAPI
from api.routes import templates, forms
from api.errors.handlers import register_exception_handlers

app = FastAPI()

# Register exception handlers
register_exception_handlers(app)

app.include_router(templates.router)
app.include_router(forms.router)