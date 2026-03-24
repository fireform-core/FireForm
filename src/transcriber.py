"""
Transcriber — offline voice-to-text using OpenAI Whisper.

Model sizes (set via WHISPER_MODEL env var):
  tiny   — fastest, lowest accuracy  (~39 MB)
  base   — default, good balance     (~74 MB)
  small  — better accuracy           (~244 MB)
  medium — high accuracy             (~769 MB)
  large  — best accuracy             (~1550 MB)

FireForm is privacy-first: all transcription runs locally.
No audio data leaves the machine.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {".wav", ".mp3", ".m4a", ".mp4", ".ogg", ".flac"}
_VALID_MODEL_SIZES = {"tiny", "base", "small", "medium", "large"}
DEFAULT_MODEL = "base"


class Transcriber:
    """
    Wraps OpenAI Whisper for local, offline audio transcription.

    The Whisper model is lazy-loaded on the first call to transcribe()
    so startup time is not penalised when the transcription feature
    is not used.

    Usage:
        t = Transcriber()                        # uses WHISPER_MODEL env var or "base"
        text = t.transcribe("recording.wav")

        t = Transcriber(model_size="small")      # explicit size
        text = t.transcribe_bytes(audio_bytes, suffix=".mp3")
    """

    def __init__(self, model_size: str | None = None) -> None:
        size = model_size or os.getenv("WHISPER_MODEL", DEFAULT_MODEL)
        if size not in _VALID_MODEL_SIZES:
            raise ValueError(
                f"Invalid model size {size!r}. "
                f"Choose from: {sorted(_VALID_MODEL_SIZES)}"
            )
        self.model_size = size
        self._model = None  # lazy-loaded

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def transcribe(self, audio_path: str | Path) -> str:
        """
        Transcribe an audio file at audio_path and return the plain text.

        Raises
        ------
        FileNotFoundError : audio file does not exist.
        ValueError        : file format not supported.
        """
        path = Path(audio_path)

        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        if path.suffix.lower() not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported audio format: {path.suffix!r}. "
                f"Supported formats: {sorted(SUPPORTED_FORMATS)}"
            )

        model = self._load_model()
        logger.info("Transcribing %s with Whisper/%s", path.name, self.model_size)

        result = model.transcribe(str(path))
        text = result["text"].strip()

        logger.info("Transcription complete — %d chars extracted", len(text))
        return text

    def transcribe_bytes(self, audio_bytes: bytes, suffix: str = ".wav") -> str:
        """
        Transcribe raw audio bytes by writing them to a temp file first.
        Used by the /transcribe endpoint which receives bytes from multipart uploads.

        The temp file is always deleted after transcription, success or failure.
        """
        suffix = suffix if suffix.startswith(".") else f".{suffix}"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)

        try:
            return self.transcribe(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    def _load_model(self):
        if self._model is None:
            try:
                import whisper
            except ImportError as exc:
                raise ImportError(
                    "openai-whisper is not installed. "
                    "Run: pip install openai-whisper"
                ) from exc

            logger.info("Loading Whisper model '%s' (first-time load)…", self.model_size)
            self._model = whisper.load_model(self.model_size)
            logger.info("Whisper model '%s' ready.", self.model_size)

        return self._model
