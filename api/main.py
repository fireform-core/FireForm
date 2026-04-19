from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from api.routes import templates, forms
from api.db.init_db import init_db
from api.errors.handlers import register_exception_handlers
from fastapi.middleware.cors import CORSMiddleware
from api.routes import forms, templates
from api.errors.handlers import register_exception_handlers

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize the database and seed it if necessary
    print("Initializing database...")
    init_db()
    yield
    # Shutdown logic goes here if needed

app = FastAPI(lifespan=lifespan)

register_exception_handlers(app)

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