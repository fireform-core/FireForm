import os
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import forms, templates
from api.errors.handlers import register_exception_handlers

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI()

register_exception_handlers(app)

default_origins = "http://127.0.0.1:5173"
allowed_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", default_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(templates.router)
app.include_router(forms.router)
