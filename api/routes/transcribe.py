"""
POST /transcribe/

Accepts a multipart audio upload and returns the plain-text transcript.
The transcript can be passed directly to POST /forms/fill as input_text,
completing the voice → structured JSON → filled PDF pipeline.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from api.errors.base import AppError

router = APIRouter(prefix="/transcribe", tags=["transcribe"])

SUPPORTED_FORMATS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}


class TranscriptResponse(BaseModel):
    filename: str
    transcript: str


@router.post("/", response_model=TranscriptResponse)
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Upload an audio file and receive a plain-text transcription.

    - Accepted formats: .wav, .mp3, .m4a, .ogg, .flac, .webm
    - All processing is local — no audio data leaves the machine.
    - The returned ``transcript`` can be used directly as ``input_text``
      in ``POST /forms/fill``.
    """
    suffix = Path(file.filename or "audio.wav").suffix.lower()

    if suffix not in SUPPORTED_FORMATS:
        raise AppError(
            f"Unsupported file format '{suffix}'. "
            f"Accepted: {', '.join(sorted(SUPPORTED_FORMATS))}",
            status_code=422,
        )

    try:
        from src.transcriber import Transcriber
    except ImportError as exc:
        raise AppError(
            "Transcription service unavailable. "
            "Install faster-whisper: pip install faster-whisper",
            status_code=503,
        ) from exc

    audio_bytes = await file.read()
    transcriber = Transcriber()
    transcript = transcriber.transcribe_bytes(audio_bytes, suffix=suffix)

    return TranscriptResponse(
        filename=file.filename or "upload",
        transcript=transcript,
    )
