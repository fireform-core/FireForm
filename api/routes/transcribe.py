from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from api.schemas.transcribe import TranscribeResponse
from src.transcriber import SUPPORTED_FORMATS, Transcriber

router = APIRouter(prefix="/transcribe", tags=["transcription"])

# Module-level singleton — Whisper model is lazy-loaded on first request.
_transcriber: Transcriber | None = None


def _get_transcriber() -> Transcriber:
    global _transcriber
    if _transcriber is None:
        _transcriber = Transcriber()
    return _transcriber


@router.post("", response_model=TranscribeResponse)
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Upload an audio file and receive a plain-text transcription.

    - Accepted formats: WAV, MP3, M4A, MP4, OGG, FLAC
    - All transcription runs locally via Whisper — no data leaves the machine.
    - Model size is configured via the `WHISPER_MODEL` environment variable
      (default: `base`). Valid values: `tiny`, `base`, `small`, `medium`, `large`.
    """
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported audio format {suffix!r}. "
                f"Accepted: {sorted(SUPPORTED_FORMATS)}"
            ),
        )

    contents = await file.read()
    transcriber = _get_transcriber()

    try:
        text = transcriber.transcribe_bytes(contents, suffix=suffix)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return TranscribeResponse(
        text=text,
        model_used=transcriber.model_size,
        audio_filename=file.filename,
    )
