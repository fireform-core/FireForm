"""System endpoints: GET /api/v1/health, /schema/incident, /schema/incident/versions.

Health contract: contracts/path/system.yaml + contracts/schemas/system.yaml
"""

import shutil
import time
from dataclasses import asdict

import requests
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.schemas.enums import HealthState
from app.api.schemas.system import (
    ComponentHealth,
    HealthComponents,
    HealthStatus,
)
from app.core.config import APP_VERSION, DATA_DIR, WHISPER_HOST
from app.db.database import engine
from app.services import llm

router = APIRouter(tags=["system"])

_START_TIME = time.monotonic()

# Tune-able thresholds. _SLOW_MS is patched in tests to trigger degraded
# without mocking wall-clock time.
_PROBE_TIMEOUT = 5
_SLOW_MS = 5_000


def _check_database() -> ComponentHealth:
    t0 = time.monotonic()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        elapsed = int((time.monotonic() - t0) * 1000)
        return ComponentHealth(status=HealthState.healthy, response_time_ms=elapsed)
    except Exception as exc:
        return ComponentHealth(status=HealthState.unhealthy, detail=str(exc))


def _check_llm() -> ComponentHealth:
    health = ComponentHealth(**asdict(llm.get_llm().health()))
    if health.status == HealthState.healthy and (health.response_time_ms or 0) > _SLOW_MS:
        health.status = HealthState.degraded
    return health


def _check_whisper() -> ComponentHealth:
    # The onerahmet/openai-whisper-asr-webservice image does not expose /health.
    # Both compose files probe /docs (a FastAPI auto-endpoint always present).
    t0 = time.monotonic()
    try:
        resp = requests.get(f"{WHISPER_HOST}/docs", timeout=_PROBE_TIMEOUT)
        resp.raise_for_status()
        elapsed = int((time.monotonic() - t0) * 1000)
        return ComponentHealth(status=HealthState.healthy, response_time_ms=elapsed)
    except requests.exceptions.RequestException as exc:
        return ComponentHealth(status=HealthState.unhealthy, detail=str(exc))


def _check_storage() -> ComponentHealth:
    try:
        usage = shutil.disk_usage(DATA_DIR)
        disk_free_gb = round(usage.free / (1024 ** 3), 2)
        return ComponentHealth(status=HealthState.healthy, disk_free_gb=disk_free_gb)
    except OSError as exc:
        return ComponentHealth(status=HealthState.unhealthy, detail=str(exc))


@router.get(
    "/health",
    responses={
        200: {"model": HealthStatus, "description": "System healthy or degraded"},
        503: {"model": HealthStatus, "description": "System unhealthy, cannot serve requests"},
    },
    summary="System health check",
)
def get_health():
    database = _check_database()
    llm_health = _check_llm()
    whisper = _check_whisper()
    storage = _check_storage()

    components = HealthComponents(
        database=database, llm=llm_health, whisper=whisper, storage=storage
    )

    statuses = {database.status, llm_health.status, whisper.status, storage.status}

    if database.status == HealthState.unhealthy:
        overall = HealthState.unhealthy
    elif HealthState.unhealthy in statuses or HealthState.degraded in statuses:
        overall = HealthState.degraded
    else:
        overall = HealthState.healthy

    body = HealthStatus(
        status=overall,
        version=APP_VERSION,
        uptime_seconds=int(time.monotonic() - _START_TIME),
        components=components,
    )

    http_status = 503 if overall == HealthState.unhealthy else 200
    return JSONResponse(
        content=body.model_dump(exclude_none=True),
        status_code=http_status,
    )


@router.get("/schema/incident", summary="Get canonical incident JSON Schema")
def get_schema_incident():
    return JSONResponse(
        status_code=501,
        content={
            "error_code": "NOT_IMPLEMENTED",
            "message": "Incident schema not yet finalised — see issue #555",
        },
    )


@router.get("/schema/incident/versions", summary="Get incident schema version history")
def get_schema_versions():
    return JSONResponse(
        status_code=501,
        content={
            "error_code": "NOT_IMPLEMENTED",
            "message": "Schema version history not yet available — see issue #555",
        },
    )
