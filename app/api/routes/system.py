"""System endpoints: GET /api/v1/health, /schema/incident, /schema/incident/versions.

Health contract: contracts/path/system.yaml + contracts/schemas/system.yaml
"""

import shutil
import time

import requests
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.schemas.system import (
    ComponentHealth,
    HealthComponents,
    HealthStatus,
    ModelInfo,
)
from app.core.config import APP_VERSION, DATA_DIR, OLLAMA_HOST, WHISPER_HOST
from app.db.database import engine

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
        return ComponentHealth(status="healthy", response_time_ms=elapsed)
    except Exception as exc:
        return ComponentHealth(status="unhealthy", detail=str(exc))


def _check_ollama() -> ComponentHealth:
    t0 = time.monotonic()
    try:
        tags_resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=_PROBE_TIMEOUT)
        tags_resp.raise_for_status()
        elapsed = int((time.monotonic() - t0) * 1000)

        tags_data = tags_resp.json()

        ollama_version: str | None = None
        try:
            ver_resp = requests.get(f"{OLLAMA_HOST}/api/version", timeout=_PROBE_TIMEOUT)
            ver_resp.raise_for_status()
            ollama_version = ver_resp.json().get("version")
        except Exception:
            pass

        running_names: set[str] = set()
        model_loaded: str | None = None
        try:
            ps_resp = requests.get(f"{OLLAMA_HOST}/api/ps", timeout=_PROBE_TIMEOUT)
            ps_resp.raise_for_status()
            running = ps_resp.json().get("models", [])
            running_names = {m.get("name", "") for m in running}
            if running:
                model_loaded = running[0].get("name")
        except Exception:
            pass

        raw_models = tags_data.get("models", [])
        models_available: list[ModelInfo] = []
        for m in raw_models:
            name = m.get("name", "")
            size_gb = round(m.get("size", 0) / (1024 ** 3), 2)
            quantization = m.get("details", {}).get("quantization_level")
            models_available.append(
                ModelInfo(name=name, size_gb=size_gb, quantization=quantization, loaded=name in running_names)
            )

        status = "degraded" if elapsed > _SLOW_MS else "healthy"

        return ComponentHealth(
            status=status,
            response_time_ms=elapsed,
            model_loaded=model_loaded,
            ollama_version=ollama_version,
            models_available=models_available if models_available else None,
            # current_load is always None — Ollama exposes no queue-depth API;
            # populating it would require fabricating data.
            current_load=None,
        )
    except requests.exceptions.RequestException as exc:
        return ComponentHealth(status="unhealthy", detail=str(exc))


def _check_whisper() -> ComponentHealth:
    # The onerahmet/openai-whisper-asr-webservice image does not expose /health.
    # Both compose files probe /docs (a FastAPI auto-endpoint always present).
    t0 = time.monotonic()
    try:
        resp = requests.get(f"{WHISPER_HOST}/docs", timeout=_PROBE_TIMEOUT)
        resp.raise_for_status()
        elapsed = int((time.monotonic() - t0) * 1000)
        return ComponentHealth(status="healthy", response_time_ms=elapsed)
    except requests.exceptions.RequestException as exc:
        return ComponentHealth(status="unhealthy", detail=str(exc))


def _check_storage() -> ComponentHealth:
    try:
        usage = shutil.disk_usage(DATA_DIR)
        disk_free_gb = round(usage.free / (1024 ** 3), 2)
        return ComponentHealth(status="healthy", disk_free_gb=disk_free_gb)
    except OSError as exc:
        return ComponentHealth(status="unhealthy", detail=str(exc))


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
    ollama = _check_ollama()
    whisper = _check_whisper()
    storage = _check_storage()

    components = HealthComponents(
        database=database, ollama=ollama, whisper=whisper, storage=storage
    )

    statuses = {database.status, ollama.status, whisper.status, storage.status}

    if database.status == "unhealthy":
        overall = "unhealthy"
    elif "unhealthy" in statuses or "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    body = HealthStatus(
        status=overall,
        version=APP_VERSION,
        uptime_seconds=int(time.monotonic() - _START_TIME),
        components=components,
    )

    http_status = 503 if overall == "unhealthy" else 200
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
