"""Application lifespan: startup and shutdown hooks."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.init_db import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    init_db()
    yield
