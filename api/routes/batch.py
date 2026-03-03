"""
Batch fill endpoint — the "report once, file everywhere" API.

POST /forms/fill/batch

This endpoint is the architectural completion of FireForm's core promise.
A firefighter records one incident transcript. This endpoint:

  1. Extracts a canonical incident record from the transcript in a SINGLE
     LLM call (all N agency forms share this extraction).

  2. Maps the canonical record to each agency template's field schema
     CONCURRENTLY via asyncio.gather() — N fast mapping calls in parallel
     instead of N * F sequential full-transcript extractions.

  3. Fills all N PDFs concurrently in a ThreadPoolExecutor (pdfrw is
     synchronous; offloading prevents event loop blocking).

  4. Persists a BatchSubmission record with the full canonical extraction
     including per-field evidence attribution (verbatim transcript quotes)
     alongside individual FormSubmission records per template.

  5. Returns everything in a single response: per-template PDF paths,
     success/failure per template, and the complete evidence report.

Time complexity improvement:
  Sequential per-form extraction:  O(T * F) LLM calls
  Batch canonical + mapping:       O(1 + T) LLM calls
  Example (5 agencies, 10 fields): 50 calls → 6 calls

GET /forms/batches/{batch_id}       — lightweight status + output paths
GET /forms/batches/{batch_id}/audit — full evidence trail for legal compliance
"""

import asyncio

from fastapi import APIRouter, Depends
from sqlmodel import Session

from api.deps import get_db
from api.schemas.batch import (
    BatchFill,
    BatchFillResponse,
    BatchStatusResponse,
    AuditResponse,
    TemplateResult,
    EvidenceField,
)
from api.db.repositories import get_template, create_form, create_batch, get_batch
from api.db.models import FormSubmission, BatchSubmission
from api.errors.base import AppError
from src.extractor import IncidentExtractor

router = APIRouter(prefix="/forms", tags=["batch"])


@router.post("/fill/batch", response_model=BatchFillResponse)
async def batch_fill(body: BatchFill, db: Session = Depends(get_db)):
    """
    Fill multiple agency-specific PDF forms from a single incident transcript.

    Extraction runs once (canonical pass) then maps to each template concurrently.
    Partial success is tolerated — if one template fails (bad PDF path, mapping
    error), the others still complete and the batch status is reported as "partial".
    """
    # ── Validate all templates exist upfront ──────────────────────────────────
    templates = {}
    for tid in body.template_ids:
        tpl = get_template(db, tid)
        if not tpl:
            raise AppError(f"Template {tid} not found", status_code=404)
        templates[tid] = tpl

    # ── Pass 1: single canonical extraction ───────────────────────────────────
    extractor = IncidentExtractor(body.input_text)
    canonical = await extractor.async_extract_canonical()
    evidence_report = IncidentExtractor.build_evidence_report(canonical)

    # ── Pass 2: concurrent mapping to each template ───────────────────────────
    import httpx

    async with httpx.AsyncClient(timeout=120.0) as client:
        mapping_tasks = [
            extractor.async_map_to_template(client, canonical, tpl.fields)
            for tpl in templates.values()
        ]
        mappings = await asyncio.gather(*mapping_tasks, return_exceptions=True)

    # mappings[i] corresponds to templates.values()[i]
    template_list = list(templates.values())
    template_id_list = list(templates.keys())

    # ── Pass 3: concurrent PDF fill in thread pool ────────────────────────────
    loop = asyncio.get_running_loop()

    async def _fill_one(tpl, data: dict) -> str:
        from src.filler import Filler
        filler = Filler()
        return await loop.run_in_executor(
            None,
            lambda: filler.fill_form_with_data(tpl.pdf_path, data),
        )

    fill_tasks = []
    failed_at_mapping: dict[int, str] = {}

    for i, (tpl, mapping) in enumerate(zip(template_list, mappings)):
        if isinstance(mapping, Exception):
            failed_at_mapping[template_id_list[i]] = str(mapping)
            fill_tasks.append(asyncio.sleep(0))  # placeholder
        else:
            fill_tasks.append(_fill_one(tpl, mapping))

    fill_results = await asyncio.gather(*fill_tasks, return_exceptions=True)

    # ── Persist FormSubmission per template + collect results ─────────────────
    results: list[TemplateResult] = []
    submission_ids: list[int] = []
    output_paths: dict[str, str | None] = {}
    errors: dict[str, str] = {}

    for i, tpl in enumerate(template_list):
        tid = template_id_list[i]

        if tid in failed_at_mapping:
            err = failed_at_mapping[tid]
            results.append(TemplateResult(
                template_id=tid, status="failed",
                submission_id=None, output_pdf_path=None, error=err,
            ))
            errors[str(tid)] = err
            output_paths[str(tid)] = None
            continue

        pdf_result = fill_results[i]
        if isinstance(pdf_result, Exception):
            err = str(pdf_result)
            results.append(TemplateResult(
                template_id=tid, status="failed",
                submission_id=None, output_pdf_path=None, error=err,
            ))
            errors[str(tid)] = err
            output_paths[str(tid)] = None
            continue

        submission = FormSubmission(
            template_id=tid,
            input_text=body.input_text,
            output_pdf_path=pdf_result,
        )
        saved = create_form(db, submission)
        submission_ids.append(saved.id)
        output_paths[str(tid)] = pdf_result
        results.append(TemplateResult(
            template_id=tid, status="complete",
            submission_id=saved.id, output_pdf_path=pdf_result, error=None,
        ))

    # ── Determine overall batch status ────────────────────────────────────────
    total_succeeded = sum(1 for r in results if r.status == "complete")
    total_failed = len(results) - total_succeeded

    if total_failed == 0:
        status = "complete"
    elif total_succeeded == 0:
        status = "failed"
    else:
        status = "partial"

    # ── Persist BatchSubmission ───────────────────────────────────────────────
    batch = BatchSubmission(
        status=status,
        input_text=body.input_text,
        canonical_extraction=canonical,
        evidence_report=evidence_report,
        template_ids=body.template_ids,
        submission_ids=submission_ids if submission_ids else None,
        output_paths=output_paths,
        errors=errors if errors else None,
    )
    saved_batch = create_batch(db, batch)

    # ── Build response ────────────────────────────────────────────────────────
    # Convert evidence_report to EvidenceField instances for schema validation
    typed_evidence = {
        k: EvidenceField(
            value=v.get("value"),
            evidence=v.get("evidence"),
            confidence=v.get("confidence", "low"),
        )
        for k, v in evidence_report.items()
    } if evidence_report else None

    return BatchFillResponse(
        batch_id=saved_batch.id,
        status=status,
        input_text=body.input_text,
        template_ids=body.template_ids,
        results=results,
        evidence_report=typed_evidence,
        total_requested=len(body.template_ids),
        total_succeeded=total_succeeded,
        total_failed=total_failed,
        created_at=saved_batch.created_at,
    )


@router.get("/batches/{batch_id}", response_model=BatchStatusResponse)
def get_batch_status(batch_id: str, db: Session = Depends(get_db)):
    """
    Lightweight status check for a completed batch submission.
    Returns per-template output_paths and any errors without the full
    canonical extraction payload. Use /audit for the full evidence trail.
    """
    batch = get_batch(db, batch_id)
    if not batch:
        raise AppError("Batch not found", status_code=404)
    return batch


@router.get("/batches/{batch_id}/audit", response_model=AuditResponse)
def get_batch_audit(batch_id: str, db: Session = Depends(get_db)):
    """
    Returns the full evidence trail for a batch submission.

    For each canonical incident category that was extracted, the response
    includes the extracted value, the verbatim transcript quote used as
    evidence, and the confidence level. This endpoint exists specifically
    for legal compliance and chain-of-custody verification: supervisors and
    legal teams can confirm that every value in every filed form is traceable
    to a specific statement in the original incident transcript.
    """
    batch = get_batch(db, batch_id)
    if not batch:
        raise AppError("Batch not found", status_code=404)
    return AuditResponse(
        batch_id=batch.id,
        input_text=batch.input_text,
        canonical_extraction=batch.canonical_extraction,
        evidence_report=batch.evidence_report,
        created_at=batch.created_at,
    )
