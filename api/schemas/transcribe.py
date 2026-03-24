from pydantic import BaseModel


class TranscribeResponse(BaseModel):
    text: str
    model_used: str
    audio_filename: str
