import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import forms, templates
from api.errors.handlers import register_exception_handlers

app = FastAPI()

# Register global exception handlers before middleware
register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(templates.router)
app.include_router(forms.router)