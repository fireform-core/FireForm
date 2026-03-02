import logging
from fastapi import FastAPI
from api.routes import templates, forms
from api.errors.handlers import register_exception_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI()

register_exception_handlers(app)

app.include_router(templates.router)
app.include_router(forms.router)
