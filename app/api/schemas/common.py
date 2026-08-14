from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.api.schemas.enums import JobStatus, JobType


class ValidationErrorItem(BaseModel):
    model_config = ConfigDict()
    field: str | None = None
    issue: str | None = None
    value: Any = None


class ErrorResponse(BaseModel):
    model_config = ConfigDict()
    error_code: str
    message: str
    detail: dict[str, Any] | None = None
    retry_after_seconds: int | None = None
    validation_errors: list[ValidationErrorItem] | None = None


class Pagination(BaseModel):
    model_config = ConfigDict()
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_prev: bool


class AsyncJobResponse(BaseModel):
    model_config = ConfigDict()
    job_id: str
    job_type: JobType | None = None
    status: JobStatus
    estimated_seconds: int | None = None
    poll_url: str | None = None


class Job(BaseModel):
    model_config = ConfigDict()
    job_id: str
    job_type: JobType
    status: JobStatus
    progress_percent: int | None = None
    result_url: str | None = None
    error: ErrorResponse | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
