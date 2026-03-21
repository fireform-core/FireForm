
from fastapi import APIRouter, UploadFile, File, Query
from fastapi.responses import JSONResponse
from api.errors.base import AppError
from src.transcriber import transcribe_audio

router = APIRouter(prefix="/transcribe", tags=["transcription"])

ALLOWED_EXTENSIONS = {".mp3", ".mp4", ".wav", ".m4a", ".ogg", ".webm", ".flac"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.post("")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Query(
        default=None,
        description="Optional language code e.g. 'en', 'fr', 'es'. "
                    "Leave empty for auto-detection."
    )
):
    """
    Transcribe an audio file to text using faster-whisper.

    Upload any audio file (wav, mp3, m4a, webm, ogg).
    Returns transcript text ready to pass directly into POST /forms/fill.

    Works CPU-only — no GPU required.
    Typical transcription time: 2-5s for a 1-minute recording.

    Example workflow:
      1. POST /transcribe  → get transcript
      2. POST /forms/fill  → fill PDF from transcript
    """
    # Validate file extension
    from pathlib import Path
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise AppError(
            f"Unsupported file type '{ext}'. "
            f"Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            status_code=422
        )

    # Read and validate file size
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise AppError(
            f"File too large ({len(file_bytes) // (1024*1024)}MB). "
            "Maximum allowed size is 50MB.",
            status_code=413
        )

    if len(file_bytes) == 0:
        raise AppError("Uploaded file is empty.", status_code=422)

    try:
        result = transcribe_audio(
            file_bytes=file_bytes,
            filename=file.filename or "audio.wav",
            language=language or None
        )
    except RuntimeError as e:
        raise AppError(str(e), status_code=503)
    except Exception as e:
        raise AppError(
            f"Transcription failed: {str(e)}",
            status_code=500
        )

    return {
        "transcript":            result["transcript"],
        "language":              result["language"],
        "language_probability":  result["language_probability"],
        "duration_seconds":      result["duration"],
        "hint": "Pass 'transcript' directly as 'input_text' to POST /forms/fill"
    }