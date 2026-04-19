import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel

from api.db.database import engine
from api.routes import forms, templates
from api.errors.handlers import register_exception_handlers
from api.middleware.rate_limiter import register_rate_limiter

logger = logging.getLogger("fireform")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting FireForm — initializing database tables")
    SQLModel.metadata.create_all(engine)
    logger.info("Database tables ready")
    yield
    logger.info("Shutting down FireForm")


app = FastAPI(
    title="FireForm API",
    description="AI-powered PDF form filling for first responders",
    version="0.1.0",
    lifespan=lifespan,
)

register_exception_handlers(app)
register_rate_limiter(app)

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


@app.get("/health", tags=["system"])
def health_check():
    return {"status": "healthy", "service": "fireform"}