import uuid as uuid_mod
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel
from sqlmodel.sql.sqltypes import AutoString

from app.api.schemas.enums import (
    ExtractionStatus,
    FormStatus,
    FormType,
    InputStatus,
    InputType,
    JobStatus,
    OutputFormat,
    PeriodType,
    ReportStatus,
)


class Template(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    fields: dict = Field(sa_column=Column(JSON, nullable=False))
    pdf_path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FormSubmission(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    template_id: int = Field(foreign_key="template.id")
    input_id: UUID | None = Field(default=None, foreign_key="inputs.input_id")
    input_text: str
    output_pdf_path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Job(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(default_factory=lambda: str(uuid_mod.uuid4()), index=True, unique=True)
    celery_task_id: str = Field(index=True)
    job_type: str = Field(default="form_generation")
    template_id: int | None = Field(default=None, foreign_key="template.id")
    input_text: str | None = None
    status: str = Field(default="queued")
    progress_percent: int = Field(default=0)
    result_url: str | None = None
    error: dict | None = Field(default=None, sa_column=Column(JSON))
    model: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# v1 contract models
# ---------------------------------------------------------------------------

class Input(SQLModel, table=True):
    __tablename__ = "inputs"

    input_id: UUID = Field(default_factory=uuid4, primary_key=True)
    # sa_column required on all str-Enum fields: without it SQLModel emits
    # sa.Enum(native_enum=True) which creates a Postgres ENUM type — hard to
    # migrate and inconsistent with the VARCHAR approach used in migration 001.
    input_type: InputType = Field(sa_column=Column(AutoString, nullable=False))
    status: InputStatus = Field(
        default=InputStatus.queued, sa_column=Column(AutoString, nullable=False)
    )
    transcript: str | None = None
    original_filename: str | None = None
    audio_duration_seconds: float | None = None
    character_count: int | None = None
    word_count: int | None = None
    station_id: str | None = None
    responder_badge: str | None = None
    incident_date_hint: date | None = None
    error_detail: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Extraction(SQLModel, table=True):
    __tablename__ = "extractions"

    extract_id: UUID = Field(default_factory=uuid4, primary_key=True)
    input_id: UUID = Field(foreign_key="inputs.input_id")
    status: ExtractionStatus = Field(
        default=ExtractionStatus.processing, sa_column=Column(AutoString, nullable=False)
    )
    started_at: datetime | None = None
    completed_at: datetime | None = None
    model_used: str | None = None
    processing_time_seconds: float | None = None
    # Full IncidentContract superset blob; stores partial result while processing,
    # final canonical JSON when status=completed.
    incident_contract: dict | None = Field(default=None, sa_column=Column(JSON))
    # Audit trail of manual corrections applied via PATCH /extract/{id}.
    corrections: list | None = Field(default=None, sa_column=Column(JSON))
    error_type: str | None = None
    error_detail: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Incident(SQLModel, table=True):
    __tablename__ = "incidents"

    incident_id: UUID = Field(default_factory=uuid4, primary_key=True)
    extract_id: UUID = Field(foreign_key="extractions.extract_id")
    incident_number: str | None = None
    status: ReportStatus = Field(
        default=ReportStatus.draft, sa_column=Column(AutoString, nullable=False)
    )
    incident_name: str | None = None
    incident_type: str | None = None
    incident_date: date | None = None
    tags: list | None = Field(default=None, sa_column=Column(JSON))
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    deleted_at: datetime | None = None


class Form(SQLModel, table=True):
    __tablename__ = "forms"

    form_id: UUID = Field(default_factory=uuid4, primary_key=True)
    form_type: FormType = Field(sa_column=Column(AutoString, nullable=False))
    status: FormStatus = Field(
        default=FormStatus.queued, sa_column=Column(AutoString, nullable=False)
    )
    extract_id: UUID = Field(foreign_key="extractions.extract_id")
    incident_id: UUID | None = Field(default=None, foreign_key="incidents.incident_id")
    # Plain UUID, no FK constraint — pending contract Job model resolution (#544 decision A).
    job_id: UUID | None = None
    completed_at: datetime | None = None
    pdf_ready: bool = Field(default=False)
    json_ready: bool = Field(default=False)
    field_mapping_summary: dict | None = Field(default=None, sa_column=Column(JSON))
    pdf_path: str | None = None
    json_data: dict | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Report(SQLModel, table=True):
    __tablename__ = "reports"

    report_id: UUID = Field(default_factory=uuid4, primary_key=True)
    period_type: PeriodType = Field(sa_column=Column(AutoString, nullable=False))
    period_label: str | None = None
    year: int
    month: int | None = None
    quarter: int | None = None
    # Named output_format (not format) to avoid shadowing the Python builtin.
    output_format: OutputFormat = Field(sa_column=Column(AutoString, nullable=False))
    status: JobStatus = Field(
        default=JobStatus.queued, sa_column=Column(AutoString, nullable=False)
    )
    generated_at: datetime | None = None
    summary: dict | None = Field(default=None, sa_column=Column(JSON))
    # Plain UUID, no FK constraint — pending contract Job model resolution (#544 decision A).
    job_id: UUID | None = None
    pdf_path: str | None = None
    json_data: dict | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))