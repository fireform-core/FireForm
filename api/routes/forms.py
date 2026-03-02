import json as json_mod
import asyncio

from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlmodel import Session
from api.deps import get_db
from api.schemas.forms import FormFill, FormFillResponse, AsyncFillSubmitted, JobStatusResponse
from api.db.repositories import create_form, get_template, create_job, get_job, update_job
from api.db.models import FormSubmission, FillJob
from api.errors.base import AppError
from src.controller import Controller

router = APIRouter(prefix="/forms", tags=["forms"])


@router.post("/fill", response_model=FormFillResponse)
def fill_form(form: FormFill, db: Session = Depends(get_db)):
    template = get_template(db, form.template_id)
    if not template:
        raise AppError("Template not found", status_code=404)

    controller = Controller()
    path = controller.fill_form(
        user_input=form.input_text,
        fields=template.fields,
        pdf_form_path=template.pdf_path,
    )

    submission = FormSubmission(**form.model_dump(), output_pdf_path=path)
    return create_form(db, submission)


@router.post("/fill/stream")
async def fill_form_stream(form: FormFill, db: Session = Depends(get_db)):
    """
    SSE endpoint. Returns text/event-stream.

    Runs field extraction concurrently (all fields in parallel via httpx.AsyncClient)
    and pushes a JSON event to the client as each field completes — no waiting for
    the full batch. After all fields are resolved a low-confidence retry pass runs
    on any null fields, then the PDF is filled and a final 'complete' event is sent.

    Event shapes:
      {"field": "...", "value": "...", "confidence": "high|medium|low", "phase": "initial|retry"}
      {"status": "complete", "submission_id": <int>, "output_pdf_path": "..."}
      {"status": "failed", "error": "..."}
    """
    template = get_template(db, form.template_id)
    if not template:
        raise AppError("Template not found", status_code=404)

    async def event_stream():
        from src.llm import LLM
        from src.filler import Filler

        llm = LLM(transcript_text=form.input_text, target_fields=template.fields)
        filler = Filler()

        try:
            # Stream field-by-field progress as each concurrent extraction completes
            async for event in llm.async_extract_all_streaming():
                yield f"data: {json_mod.dumps(event)}\n\n"

            # PDF fill is synchronous (pdfrw) — offload to thread pool to avoid blocking
            loop = asyncio.get_running_loop()
            output_path = await loop.run_in_executor(
                None,
                lambda: filler.fill_form_with_data(template.pdf_path, llm.get_data()),
            )

            submission = FormSubmission(**form.model_dump(), output_pdf_path=output_path)
            create_form(db, submission)

            yield f"data: {json_mod.dumps({'status': 'complete', 'submission_id': submission.id, 'output_pdf_path': output_path})}\n\n"

        except Exception as exc:
            yield f"data: {json_mod.dumps({'status': 'failed', 'error': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/fill/async", status_code=202, response_model=AsyncFillSubmitted)
async def fill_form_async(
    form: FormFill,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Accepts a fill request and returns HTTP 202 immediately with a job_id.
    The extraction + PDF fill runs as a background task while the client is free
    to poll GET /forms/jobs/{job_id} for incremental status and partial results.
    """
    template = get_template(db, form.template_id)
    if not template:
        raise AppError("Template not found", status_code=404)

    job = FillJob(
        template_id=form.template_id,
        input_text=form.input_text,
        status="pending",
    )
    create_job(db, job)

    # Snapshot template data — the request session closes after the response
    template_fields = template.fields
    template_pdf_path = template.pdf_path

    background_tasks.add_task(
        _run_fill_job, job.id, template_fields, template_pdf_path, form.input_text
    )

    return AsyncFillSubmitted(job_id=job.id, status="pending")


async def _run_fill_job(
    job_id: str,
    template_fields: dict,
    template_pdf_path: str,
    input_text: str,
) -> None:
    """
    Background coroutine that executes the full async extraction + PDF fill pipeline
    and persists incremental progress to the FillJob record so polling clients see
    partial_results update in real time.
    """
    from sqlmodel import Session as SyncSession
    from api.db.database import engine

    with SyncSession(engine) as session:
        update_job(session, job_id, status="running")
        partial: dict[str, str | None] = {}
        confidence: dict[str, str] = {}

        try:
            from src.llm import LLM
            from src.filler import Filler

            llm = LLM(transcript_text=input_text, target_fields=template_fields)

            async for event in llm.async_extract_all_streaming():
                if "field" in event:
                    partial[event["field"]] = event["value"]
                    confidence[event["field"]] = event["confidence"]
                    # Persist incremental results so polling clients see live progress
                    update_job(
                        session,
                        job_id,
                        partial_results=dict(partial),
                        field_confidence=dict(confidence),
                    )

            # PDF fill is synchronous — run in thread pool
            filler = Filler()
            loop = asyncio.get_running_loop()
            output_path = await loop.run_in_executor(
                None,
                lambda: filler.fill_form_with_data(template_pdf_path, llm.get_data()),
            )

            update_job(
                session,
                job_id,
                status="complete",
                output_pdf_path=output_path,
                partial_results=dict(partial),
                field_confidence=dict(confidence),
            )

        except Exception as exc:
            update_job(session, job_id, status="failed", error_message=str(exc))


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """
    Poll the status of an async fill job submitted via POST /forms/fill/async.
    Returns the current status, any incrementally extracted partial_results,
    per-field confidence scores, and the output_pdf_path once complete.
    """
    job = get_job(db, job_id)
    if not job:
        raise AppError("Job not found", status_code=404)
    return job


