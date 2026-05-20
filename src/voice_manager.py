import os
import whisper


class VoiceManager:
    """Transcribes audio files to text using OpenAI Whisper (local, offline)."""

    SUPPORTED_FORMATS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}

    def __init__(self, model_name=None):
        """
        Initialize VoiceManager with a Whisper model.

        Args:
            model_name: Whisper model size ('tiny', 'base', 'small',
                        'medium', 'large'). Defaults to WHISPER_MODEL
                        env var or 'base'.
        """
        model_name = model_name or os.getenv("WHISPER_MODEL", "base")
        self.model = whisper.load_model(model_name)

    def transcribe(self, audio_path):
        """
        Transcribe an audio file to text.

        Args:
            audio_path: Path to the audio file.

        Returns:
            str: The transcribed text.

        Raises:
            FileNotFoundError: If the audio file does not exist.
            ValueError: If the format is unsupported or no speech detected.
        """
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        ext = os.path.splitext(audio_path)[1].lower()
        if ext not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported audio format '{ext}'. "
                f"Supported: {', '.join(sorted(self.SUPPORTED_FORMATS))}"
            )

        result = self.model.transcribe(audio_path)
        transcript = result["text"].strip()

        if not transcript:
            raise ValueError(f"No speech detected in audio file: {audio_path}")

        return transcript
