from datetime import date
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.exceptions import RequestValidationError
from sqlmodel import Session

from app.api.deps import get_db
from app.api.schemas.enums import InputStatus
from app.api.schemas.input import (
    InputRecordResponse,
    TextInputRequest,
    TextInputResponse,
    VoiceInputResponse,
)
from app.core.config import (
    ALLOWED_AUDIO_EXTENSIONS,
    AUDIO_CONTENT_TYPES,
    ESTIMATED_TRANSCRIPTION_SECONDS,
    INPUT_POLL_INTERVAL_SECONDS,
)
from app.core.errors.base import AppError
from app.db.repositories import create_input
from app.db.repositories import get_input as repo_get_input
from app.services.input import InputService
from app.services.whisper import check_whisper_available

router = APIRouter(prefix="/input", tags=["input"])

_MAX_AUDIO_BYTES = 500 * 1024 * 1024  # 500 MB


@router.post("/voice", response_model=VoiceInputResponse, status_code=201)
def submit_voice_input(
    audio_file: UploadFile = File(...),
    station_id: str | None = Form(default=None),
    responder_badge: str | None = Form(default=None),
    incident_date_hint: date | None = Form(default=None),
    db: Session = Depends(get_db),
):
    # 415 — format check (HTTP concern, before any I/O)
    filename = audio_file.filename or ""
    ext = Path(filename).suffix.lstrip(".").lower()
    if not ext or ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise AppError(
            "Audio format not supported. Accepted formats: wav, mp3, m4a, ogg, webm",
            status_code=415,
            error_code="UNSUPPORTED_FORMAT",
            detail={"accepted_formats": list(AUDIO_CONTENT_TYPES)},
        )

    # 413 — size check: fast path via Content-Length (no read), fallback via len(bytes)
    if audio_file.size is not None and audio_file.size > _MAX_AUDIO_BYTES:
        raise AppError(
            "Audio file exceeds maximum size of 500MB",
            status_code=413,
            error_code="FILE_TOO_LARGE",
            detail={"max_size_bytes": _MAX_AUDIO_BYTES, "received_size_bytes": audio_file.size},
        )
    content = audio_file.file.read()
    if len(content) > _MAX_AUDIO_BYTES:
        raise AppError(
            "Audio file exceeds maximum size of 500MB",
            status_code=413,
            error_code="FILE_TOO_LARGE",
            detail={"max_size_bytes": _MAX_AUDIO_BYTES, "received_size_bytes": len(content)},
        )

    # 503 — Whisper availability (HTTP concern)
    if not check_whisper_available():
        raise AppError(
            "Whisper transcription service is not available",
            status_code=503,
            error_code="STT_UNAVAILABLE",
        )

    svc = InputService()
    record, job = svc.process_voice_upload(
        session=db,
        audio_content=content,
        ext=ext,
        filename=filename,
        station_id=station_id,
        responder_badge=responder_badge,
        incident_date_hint=incident_date_hint,
    )

    return VoiceInputResponse(
        input_id=record.input_id,
        status=record.status,
        input_type=record.input_type,
        job_id=job.job_id,
        poll_url=f"/api/v1/input/{record.input_id}",
        estimated_processing_seconds=ESTIMATED_TRANSCRIPTION_SECONDS,
        created_at=record.created_at,
    )


@router.post("/text", response_model=TextInputResponse, status_code=201)
def submit_text_input(body: TextInputRequest, db: Session = Depends(get_db)):
    if len(body.narrative) > 50_000:
        raise AppError(
            "Narrative exceeds maximum length of 50,000 characters",
            status_code=413,
            error_code="NARRATIVE_TOO_LONG",
            detail={"max_characters": 50_000, "received_characters": len(body.narrative)},
        )

    svc = InputService()
    try:
        record = svc.build_text_input(
            narrative=body.narrative,
            station_id=body.station_id,
            responder_badge=body.responder_badge,
            incident_date_hint=body.incident_date_hint,
        )
    except ValueError as exc:
        raise RequestValidationError(
            errors=[
                {
                    "loc": ("body", "narrative"),
                    "msg": str(exc),
                    "input": body.narrative,
                    "type": "value_error",
                }
            ]
        )

    record = create_input(db, record)

    return TextInputResponse(
        input_id=record.input_id,
        status=record.status,
        input_type=record.input_type,
        character_count=record.character_count,
        word_count=record.word_count,
        created_at=record.created_at,
    )


@router.get("/{input_id}", response_model=InputRecordResponse)
def get_input(input_id: UUID, db: Session = Depends(get_db)):
    record = repo_get_input(db, input_id)
    if record is None:
        raise AppError(
            f"Input with ID {input_id} not found",
            status_code=404,
            error_code="INPUT_NOT_FOUND",
        )

    retry_after = (
        INPUT_POLL_INTERVAL_SECONDS
        if record.status in (InputStatus.queued, InputStatus.transcribing)
        else None
    )
    return InputRecordResponse(
        input_id=record.input_id,
        input_type=record.input_type,
        status=record.status,
        transcript=record.transcript,
        original_filename=record.original_filename,
        audio_duration_seconds=record.audio_duration_seconds,
        character_count=record.character_count,
        word_count=record.word_count,
        station_id=record.station_id,
        responder_badge=record.responder_badge,
        incident_date_hint=record.incident_date_hint,
        error_detail=record.error_detail,
        retry_after_seconds=retry_after,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
