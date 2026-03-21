from fastapi import FastAPI
from api.routes import templates, forms
from api.similarity_api import router as similarity_router
from api.errors.handlers import register_exception_handlers

app = FastAPI()
app.include_router(similarity_router)
app.include_router(templates.router)
register_exception_handlers(app)
app.include_router(forms.router)