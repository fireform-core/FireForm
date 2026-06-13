import os

import requests
from fastapi import APIRouter, Depends, File, UploadFile
from sqlmodel import Session
from api.deps import get_db
from api.schemas.forms import (
    FormFill,
    FormFillResponse,
    ModelsResponse,
    TranscriptionResponse,
)
from api.db.repositories import create_form, get_template
from api.db.models import FormSubmission
from api.errors.base import AppError
from src.controller import Controller

router = APIRouter(prefix="/forms", tags=["forms"])


@router.post("/fill", response_model=FormFillResponse)
def fill_form(form: FormFill, db: Session = Depends(get_db)):

    fetched_template = get_template(db, form.template_id)
    if not fetched_template:
        raise AppError("Template not found", status_code=404)

    controller = Controller()
    try:
        path = controller.fill_form(
            user_input=form.input_text,
            fields=fetched_template.fields,
            pdf_form_path=fetched_template.pdf_path,
            model=form.model,
        )

        # `model` is a runtime override, not a column — keep it out of the DB row.
        submission = FormSubmission(
            **form.model_dump(exclude={"model"}), output_pdf_path=path
        )
        return create_form(db, submission)
    except Exception as e:
        raise AppError(str(e), status_code=500)


@router.get("/models", response_model=ModelsResponse)
def list_models():
    """List the Whisper-independent extraction models available in the local
    Ollama instance, plus the configured default. Used by the Fill Form UI's
    model picker. Falls back to just the default if Ollama is unreachable."""
    default_model = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")

    models: list[str] = []
    try:
        response = requests.get(f"{ollama_host}/api/tags", timeout=10)
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
    whisper_host = os.getenv("WHISPER_HOST", "http://localhost:9000").rstrip("/")
    whisper_url = f"{whisper_host}/asr"

    files = {
        "audio_file": (
            audio.filename or "audio.wav",
            audio.file.read(),
            audio.content_type or "audio/wav",
        )
    }
    params = {"task": "transcribe", "output": "json", "encode": "true"}

    try:
        response = requests.post(whisper_url, params=params, files=files, timeout=120)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise AppError(
            f"Could not connect to the speech-to-text service at {whisper_url}. "
            "Please ensure the whisper service is running.",
            status_code=503,
        )
    except requests.exceptions.RequestException as e:
        raise AppError(f"Transcription failed: {e}", status_code=502)

    try:
        text = (response.json().get("text") or "").strip()
    except ValueError:
        text = response.text.strip()

    return TranscriptionResponse(text=text)
