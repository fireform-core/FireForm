"""
Voice transcription pipeline using faster-whisper (local, on-device).

No audio data ever leaves the machine — fully aligned with FireForm's
privacy-first design for first responder environments.

Supported formats: .wav, .mp3, .m4a, .ogg, .flac, .webm
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

SUPPORTED_FORMATS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}


class Transcriber:
    """
    Transcribes audio files to plain text using a locally-running Whisper model.

    Uses ``faster-whisper`` (CTranslate2 backend) for CPU-friendly inference
    with no GPU required — suitable for field deployments.

    :param model_size:    Whisper model size. "base" balances speed and accuracy
                          on CPU. Options: tiny, base, small, medium, large-v2
    :param device:        "cpu" or "cuda"
    :param compute_type:  Quantisation type. "int8" is fastest on CPU.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ImportError(
                "faster-whisper is not installed.\n"
                "Run: pip install faster-whisper\n"
                "Or add it to requirements.txt and rebuild the container."
            ) from exc

        print(f"[Transcriber] Loading Whisper model '{model_size}' on {device}...")
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        print("[Transcriber] Model ready.")

    def transcribe(self, audio_path: str | os.PathLike) -> str:
        """
        Transcribe an audio file to text.

        :param audio_path: Path to the audio file.
        :returns:          The full transcript as a single string.
        :raises FileNotFoundError: If the file does not exist.
        :raises ValueError:        If the file format is not supported.
        """
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if audio_path.suffix.lower() not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported audio format: '{audio_path.suffix}'. "
                f"Supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}"
            )

        print(f"[Transcriber] Transcribing: {audio_path.name}")
        segments, info = self._model.transcribe(str(audio_path), beam_size=5)

        transcript = " ".join(segment.text.strip() for segment in segments)

        print(f"[Transcriber] Detected language : {info.language} "
              f"(probability {info.language_probability:.2f})")
        print(f"[Transcriber] Duration          : {info.duration:.1f}s")
        print(f"[Transcriber] Transcript        : {transcript}")

        return transcript.strip()

    def transcribe_bytes(self, audio_bytes: bytes, suffix: str = ".wav") -> str:
        """
        Transcribe raw audio bytes (e.g. from an HTTP upload) without saving to disk.

        :param audio_bytes: Raw audio content.
        :param suffix:      File extension hint for the temporary file (e.g. ".mp3").
        :returns:           The full transcript as a single string.
        """
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            return self.transcribe(tmp_path)
        finally:
            os.unlink(tmp_path)
