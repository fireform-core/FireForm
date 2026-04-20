from contextlib import asynccontextmanager
import os
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from api.routes import templates, forms
from api.db.init_db import init_db
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
