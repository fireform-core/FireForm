"""Application lifespan: startup and shutdown hooks."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.init_db import init_db
from app.services import llm

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A missing key or an unnamed model is a deployment mistake. Better to stop
    # here than halfway through someone's incident report.
    llm.check_config()

    logger.info("Initializing database...")
    init_db()
    yield
