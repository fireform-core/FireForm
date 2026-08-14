from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.schemas.enums import InputStatus, InputType


class VoiceInputResponse(BaseModel):
    input_id: UUID
    status: InputStatus
    input_type: InputType
    estimated_processing_seconds: int | None = None
    created_at: datetime | None = None
    job_id: str | None = None
    poll_url: str | None = None


class TextInputRequest(BaseModel):
    narrative: str = Field(min_length=20)
    station_id: str | None = None
    responder_badge: str | None = None
    incident_date_hint: date | None = None


class TextInputResponse(BaseModel):
    input_id: UUID
    status: InputStatus
    input_type: InputType
    character_count: int | None = None
    word_count: int | None = None
    created_at: datetime | None = None


class InputRecordResponse(BaseModel):
    input_id: UUID
    input_type: InputType
    status: InputStatus
    transcript: str | None = None
    original_filename: str | None = None
    audio_duration_seconds: float | None = None
    character_count: int | None = None
    word_count: int | None = None
    station_id: str | None = None
    responder_badge: str | None = None
    incident_date_hint: date | None = None
    error_detail: str | None = None
    retry_after_seconds: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
