"""System endpoints: GET /api/v1/health, /schema/incident, /schema/incident/versions.

Health contract: contracts/path/system.yaml + contracts/schemas/system.yaml
"""

import shutil
import time

import requests
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.schemas.system import (
    ComponentHealth,
    HealthComponents,
    HealthStatus,
    SchemaFieldEntry,
    SchemaFieldSearchResponse,
)
from app.services import field_catalog, llm
from app.core.config import APP_VERSION, DATA_DIR, WHISPER_HOST
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


def _check_llm() -> ComponentHealth:
    """Health for whichever provider this deployment is configured for.

    A local provider is probed. A hosted one is not, so the model list is left
    out there too: both cost quota to answer a question the configuration
    already answers.
    """
    report = llm.health()
    status = report.status
    if status == "healthy" and report.response_time_ms and report.response_time_ms > _SLOW_MS:
        status = "degraded"

    models: list[str] | None = None
    if report.probed and status != "unhealthy":
        models = [model.name for model in llm.list_models()]

    return ComponentHealth(
        status=status,
        response_time_ms=report.response_time_ms,
        detail=report.detail,
        provider=report.provider,
        model=report.model,
        external=report.external,
        probed=report.probed,
        models_available=models,
    )


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
    provider = _check_llm()
    whisper = _check_whisper()
    storage = _check_storage()

    components = HealthComponents(
        database=database, llm=provider, whisper=whisper, storage=storage
    )

    statuses = {database.status, provider.status, whisper.status, storage.status}

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


@router.get(
    "/schema/fields",
    response_model=SchemaFieldSearchResponse,
    summary="Search or list the incident-contract field catalog",
)
def search_schema_fields(
    q: str | None = Query(None, description="Search text, matched against names, aliases and descriptions"),
    section: str | None = Query(None, description="Restrict to one top-level contract section"),
    limit: int = Query(20, ge=1, le=100, description="Caps search results, ignored when q is omitted"),
):
    hits = field_catalog.search(q, section, limit)
    return SchemaFieldSearchResponse(
        query=q,
        total=len(hits),
        schema_version=field_catalog.schema_version(),
        fields=[
            SchemaFieldEntry(
                path=entry.path,
                label=entry.label,
                field_type=entry.field_type,
                section=entry.section,
                description=entry.description,
                enum_values=list(entry.enum_values) if entry.enum_values else None,
                pii=entry.pii,
                aliases=list(entry.aliases),
                score=score,
            )
            for entry, score in hits
        ],
    )
