"""The extraction run.

Takes a queued extraction and turns it into a validated contract and a draft
incident. Order of business: read the narrative, pick the chunks worth asking
about, run them in waves, apply the deterministic post-steps, stitch one
document, then write the incident and close out the extraction and its job.

A chunk that fails does not sink the run. The narrative is the only thing every
chunk shares, so a chunk missing means those fields stay empty and the review
screen shows the gap. The run only fails when the provider itself is the
problem, unreachable or out of quota, or when nothing at all could be extracted.
A run stopped by a rate limit keeps everything the earlier waves published.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlmodel import Session

from app.api.schemas.enums import ExtractionStatus
from app.api.schemas.incident_contract import IncidentContract
from app.core.logging import get_logger
from app.db.repositories import (
    create_draft_incident,
    get_extraction,
    get_input,
    get_job_by_uuid,
    update_extraction,
    update_incident,
    update_job,
)
from app.services import llm
from app.services.extraction.defaults import apply_context, context_lines, resolve_context
from app.services.extraction.router import select_chunks
from app.services.extraction.runner import ChunkResult, run_chunks
from app.services.incidents import PROMOTED_COLUMNS, promote

logger = get_logger(__name__)

SCHEMA_VERSION = "1.1.0"
SCHEMA_NAME = "fireform_incident_contract"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stitch(results: list[ChunkResult]) -> dict[str, Any]:
    """Merge the chunk results into one contract document.

    Chunks own disjoint sub-objects, so merging is a plain assignment per chunk.
    Chunks with nothing in them are left out: an absent field means unknown.
    """
    contract: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "schema_name": SCHEMA_NAME}
    for result in results:
        if result.has_value:
            contract[result.name] = result.value
    return contract


def _completeness(results: list[ChunkResult]) -> dict[str, Any]:
    """Extraction-quality summary for extraction_metadata."""
    filled = [r for r in results if r.has_value]
    failed = [r.name for r in results if not r.ok]
    empty = [r.name for r in results if r.ok and not r.has_value]
    # A salvaged chunk kept its good fields; the ones thrown away are gaps too.
    dropped = [f"{r.name}.{path}" for r in results for path in r.dropped]
    percent = round(100 * len(filled) / len(results)) if results else 0
    return {
        "overall_percent": percent,
        "missing_fields": sorted(failed + empty + dropped),
    }


def _metadata(extraction, input_record, model_used: str, results: list[ChunkResult]) -> dict[str, Any]:
    return {
        "extract_id": str(extraction.extract_id),
        "input_id": str(extraction.input_id),
        "input_type": input_record.input_type.value
        if hasattr(input_record.input_type, "value")
        else str(input_record.input_type),
        "extracted_at": _now().isoformat(),
        "llm_model": model_used,
        "completeness": _completeness(results),
    }


def _fail(session: Session, extraction, job, error_type: str, detail: str) -> None:
    now = _now()
    extraction.status = ExtractionStatus.failed
    extraction.error_type = error_type
    extraction.error_detail = detail
    extraction.updated_at = now
    update_extraction(session, extraction)
    if job:
        job.status = "failed"
        job.error = {"error_code": error_type, "message": detail}
        job.updated_at = now
        update_job(session, job)
    logger.error("extraction %s failed (%s): %s", extraction.extract_id, error_type, detail)


def _write_incident(session: Session, extraction, contract: dict[str, Any]):
    """Create the draft incident that owns the contract from here on."""
    incident = create_draft_incident(session, extraction.extract_id)
    incident.incident_contract = contract
    promoted = promote(contract)
    for column in PROMOTED_COLUMNS:
        setattr(incident, column, promoted[column])
    incident.updated_at = _now()
    return update_incident(session, incident)


def run_extraction(
    session: Session,
    extract_id: UUID,
    job_id: str,
    defaults: dict | None = None,
    hints: dict | None = None,
) -> dict[str, Any]:
    """Run one queued extraction to completion. Returns a small result summary."""
    started = time.monotonic()
    extraction = get_extraction(session, extract_id)
    if extraction is None:
        logger.error("extraction %s no longer exists, nothing to run", extract_id)
        return {"extract_id": str(extract_id), "status": "missing"}

    job = get_job_by_uuid(session, job_id)
    input_record = get_input(session, extraction.input_id)

    now = _now()
    extraction.status = ExtractionStatus.processing
    extraction.started_at = extraction.started_at or now
    extraction.updated_at = now
    update_extraction(session, extraction)
    if job:
        job.status = "processing"
        job.updated_at = now
        update_job(session, job)

    text = (input_record.transcript if input_record else "") or ""
    if not text.strip():
        _fail(session, extraction, job, "EMPTY_INPUT", "The input has no transcript to extract from.")
        return {"extract_id": str(extract_id), "status": "failed"}

    model_used = extraction.model_used or llm.get_settings().model
    context = resolve_context(defaults)
    prompt_context = context_lines(context, hints)
    specs = select_chunks(text)

    collected: list[ChunkResult] = []

    def publish(wave: list[ChunkResult]) -> None:
        """Show what has landed so far while the remaining waves run."""
        collected.extend(wave)
        extraction.partial_result = _stitch(collected)
        extraction.updated_at = _now()
        update_extraction(session, extraction)
        if job:
            job.progress_percent = round(100 * len(collected) / len(specs)) if specs else 100
            job.updated_at = _now()
            update_job(session, job)

    try:
        results = run_chunks(specs, text, prompt_context, extraction.model_used, on_wave=publish)
    except llm.LLMRateLimitError as exc:
        # Whatever the waves already published stays on the record, so a run cut
        # short by a quota is still worth reviewing rather than starting over.
        _fail(session, extraction, job, "LLM_RATE_LIMITED", str(exc))
        return {
            "extract_id": str(extract_id),
            "status": "failed",
            "retry_after_seconds": exc.retry_after_seconds,
        }
    except (llm.LLMUnavailableError, llm.LLMAuthError) as exc:
        _fail(session, extraction, job, "LLM_UNAVAILABLE", str(exc))
        raise

    if results and not any(result.ok for result in results):
        _fail(
            session,
            extraction,
            job,
            "EXTRACTION_FAILED",
            "Every chunk was rejected by validation. Nothing could be extracted.",
        )
        return {"extract_id": str(extract_id), "status": "failed"}

    contract = apply_context(_stitch(results), context)
    contract["extraction_metadata"] = _metadata(extraction, input_record, model_used, results)

    try:
        IncidentContract.model_validate(contract)
    except ValidationError as exc:
        _fail(session, extraction, job, "EXTRACTION_FAILED", f"stitched contract is invalid: {exc}")
        raise

    incident = _write_incident(session, extraction, contract)

    now = _now()
    extraction.status = ExtractionStatus.completed
    extraction.completed_at = now
    extraction.processing_time_seconds = round(time.monotonic() - started, 2)
    extraction.model_used = model_used
    # The incident row owns the document now; the working copy goes away.
    extraction.partial_result = None
    extraction.error_type = None
    extraction.error_detail = None
    extraction.updated_at = now
    update_extraction(session, extraction)

    if job:
        job.status = "completed"
        job.progress_percent = 100
        job.result_url = f"/api/v1/extract/{extract_id}"
        job.updated_at = now
        update_job(session, job)

    failed = [result.name for result in results if not result.ok]
    logger.info(
        "extraction %s completed in %.2fs: %d/%d chunks filled, %d failed, incident %s",
        extract_id,
        extraction.processing_time_seconds,
        sum(1 for r in results if r.has_value),
        len(results),
        len(failed),
        incident.incident_id,
    )
    return {
        "extract_id": str(extract_id),
        "job_id": job_id,
        "incident_id": str(incident.incident_id),
        "status": "completed",
        "failed_chunks": failed,
    }
