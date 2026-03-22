import os
import tempfile
from pathlib import Path


def transcribe_audio(file_bytes: bytes, filename: str, language: str = None) -> dict:
    """
    Transcribe audio file using faster-whisper.
    
    Args:
        file_bytes: Raw audio file bytes
        filename: Original filename (used to detect format)
        language: Optional language code (e.g. 'en', 'fr'). None = auto-detect.
    
    Returns:
        dict with 'transcript', 'language', 'duration'
    
    Supports: mp3, mp4, wav, m4a, ogg, webm (anything ffmpeg handles)
    CPU-only — no GPU required. ~4x faster than openai-whisper, 3x less RAM.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError(
            "faster-whisper not installed. Run: pip install faster-whisper"
        )

    # Write bytes to temp file — faster-whisper needs a file path
    suffix = Path(filename).suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        # Use tiny model by default — fast, CPU-friendly, good accuracy
        # Model downloads once (~75MB) to ~/.cache/huggingface/
        model_size = os.getenv("WHISPER_MODEL", "tiny")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")

        segments, info = model.transcribe(
            tmp_path,
            language=language,
            beam_size=5,
            vad_filter=True,          # skip silent sections
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        transcript = " ".join(segment.text.strip() for segment in segments)

        return {
            "transcript": transcript.strip(),
            "language": info.language,
            "language_probability": round(info.language_probability, 2),
            "duration": round(info.duration, 1)
        }

    finally:
        os.unlink(tmp_path)