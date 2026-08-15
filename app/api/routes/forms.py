import requests
from fastapi import APIRouter, Depends, File, UploadFile, Query
from sqlmodel import Session

from app.api.deps import get_db, verify_api_key
from app.api.schemas.forms import (
    FormFill,
    FormFillResponse,
    ModelsResponse,
    TranscriptionResponse,
)
from app.core import paths
from app.core.config import OLLAMA_HOST, OLLAMA_MODEL, RETENTION_PERIOD_DAYS
from app.services.whisper import call_whisper_asr
from app.core.errors.base import AppError
from app.db.repositories import get_template, get_form_submission, delete_form_submission
from app.services.form import FormService

router = APIRouter(prefix="/forms", tags=["forms"])


@router.post("/fill", response_model=FormFillResponse)
def fill_form(form: FormFill, db: Session = Depends(get_db)):

    fetched_template = get_template(db, form.template_id)
    if not fetched_template:
        raise AppError("Template not found", status_code=404, error_code="TEMPLATE_NOT_FOUND")

    svc = FormService()
    try:
        return svc.fill_form(db, template=fetched_template, input_id=form.input_id, model=form.model)
    except AppError:
        raise
    except Exception as e:
        raise AppError(str(e), status_code=500, error_code="FORM_FILL_ERROR")


@router.get("/models", response_model=ModelsResponse)
def list_models():
    """List the Whisper-independent extraction models available in the local
    Ollama instance, plus the configured default. Used by the Fill Form UI's
    model picker. Falls back to just the default if Ollama is unreachable."""
    default_model = OLLAMA_MODEL

    models: list[str] = []
    try:
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=10)
        response.raise_for_status()
        models = [m["name"] for m in response.json().get("models", []) if m.get("name")]
    except requests.exceptions.RequestException:
        models = []

    # Always surface the configured default, even if Ollama hasn't pulled it yet.
    if default_model not in models:
        models.insert(0, default_model)

    return ModelsResponse(models=models, default=default_model)


@router.post("/transcribe", response_model=TranscriptionResponse)
def transcribe(audio: UploadFile = File(...)):
    """Forward recorded audio to the local Whisper ASR sidecar and return text.

    Mirrors the Ollama wiring: WHISPER_HOST points at the whisper service
    (http://whisper:9000 inside Docker, http://localhost:9000 otherwise). The
    audio is streamed straight through to the local STT service and never
    persisted — no PII leaves the machine.
    """
    try:
        text = call_whisper_asr(
            audio.file.read(),
            audio.filename or "audio.wav",
            audio.content_type or "audio/wav",
        )
    except ConnectionError as exc:
        raise AppError(str(exc), status_code=503, error_code="STT_UNAVAILABLE")
    except RuntimeError as exc:
        raise AppError(str(exc), status_code=502, error_code="TRANSCRIPTION_FAILED")

    return TranscriptionResponse(text=text)


@router.delete("/{submission_id}", dependencies=[Depends(verify_api_key)])
def delete_submission_endpoint(submission_id: int, db: Session = Depends(get_db)):
    sub = get_form_submission(db, submission_id)
    if not sub:
        raise AppError("Submission not found", status_code=404, error_code="SUBMISSION_NOT_FOUND")

    if sub.output_pdf_path:
        try:
            resolved_out = paths._resolve_project_file(sub.output_pdf_path)
            if resolved_out.exists() and resolved_out.is_file():
                resolved_out.unlink()
        except Exception:
            pass

    delete_form_submission(db, sub)
    return {"status": "success", "message": "Submission and associated output file deleted"}


@router.post("/purge", dependencies=[Depends(verify_api_key)])
def purge_submissions_endpoint(days: int = Query(default=None), db: Session = Depends(get_db)):
    retention_days = days if days is not None else RETENTION_PERIOD_DAYS
    purged_count = FormService().purge_submissions(db, retention_days)
    return {"status": "success", "purged_count": purged_count, "retention_days_used": retention_days}


@router.get("/submissions")
def get_submissions(db: Session = Depends(get_db)):
    return FormService().list_submissions(db)


@router.get("/submissions/analytics")
def get_submissions_analytics(db: Session = Depends(get_db)):
    return FormService().get_analytics(db)
