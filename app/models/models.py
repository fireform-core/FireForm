import uuid as uuid_mod
from uuid import UUID, uuid4
from datetime import date, datetime, timezone

from sqlalchemy import Column, Index, JSON, text
from sqlmodel import SQLModel, Field
from sqlmodel.sql.sqltypes import AutoString

from app.api.schemas.enums import (
    DetectionStatus,
    ExtractionStatus,
    FormStatus,
    FormType,
    IncidentCategory,
    InputStatus,
    InputType,
    JobStatus,
    OutputFormat,
    PeriodType,
    ReportStatus,
    TemplateStatus,
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
    # Transient contract blob held only while the job runs. Cleared once the
    # extraction completes and the contract is written to the incident row,
    # which is the single store. Extractions keep no copy of the final contract.
    partial_result: dict | None = Field(default=None, sa_column=Column(JSON))
    # Audit trail of manual corrections applied via PATCH /extract/{id}.
    corrections: list | None = Field(default=None, sa_column=Column(JSON))
    error_type: str | None = None
    error_detail: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Incident(SQLModel, table=True):
    __tablename__ = "incidents"
    __table_args__ = (
        # A department's incident number identifies one live incident. Partial
        # so a soft-deleted row does not keep its number reserved forever, and
        # so the many rows still awaiting a number do not collide on NULL.
        Index(
            "ix_incidents_number_live",
            "incident_number",
            unique=True,
            postgresql_where=text("incident_number IS NOT NULL AND deleted_at IS NULL"),
            sqlite_where=text("incident_number IS NOT NULL AND deleted_at IS NULL"),
        ),
        # Covers GET /incidents: every query excludes soft-deleted rows and
        # then sorts on incident_datetime. The status and incident_category
        # filters are left unindexed on purpose, they are low cardinality and
        # a department-sized table does not need them.
        Index("ix_incidents_live_datetime", "deleted_at", "incident_datetime"),
    )

    incident_id: UUID = Field(default_factory=uuid4, primary_key=True)
    extract_id: UUID = Field(foreign_key="extractions.extract_id")
    incident_number: str | None = None
    status: ReportStatus = Field(
        default=ReportStatus.draft, sa_column=Column(AutoString, nullable=False)
    )
    incident_name: str | None = None
    incident_type: str | None = None
    tags: list | None = Field(default=None, sa_column=Column(JSON))
    notes: str | None = None
    # The single store of the incident contract. Created as a draft when
    # extraction completes; PATCH /extract writes here, form generation reads
    # here. Nothing else keeps a copy.
    incident_contract: dict | None = Field(default=None, sa_column=Column(JSON))
    # Promoted scalars, recomputed server-side from the contract on every
    # document change. All nullable; clients never write them directly.
    incident_category: IncidentCategory | None = Field(
        default=None, sa_column=Column(AutoString, nullable=True)
    )
    incident_datetime: datetime | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    civilian_injuries: int | None = None
    civilian_fatalities: int | None = None
    responder_injuries: int | None = None
    responder_fatalities: int | None = None
    people_rescued: int | None = None
    people_evacuated: int | None = None
    structures_destroyed: int | None = None
    area_burned_ha: float | None = None
    total_loss_amount: float | None = None
    total_loss_currency: str | None = None
    call_to_arrival_seconds: int | None = None
    turnout_seconds_first_unit: int | None = None
    travel_seconds_first_unit: int | None = None
    on_scene_duration_seconds: int | None = None
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
    template_id: UUID = Field(foreign_key="form_templates.template_id")
    incident_id: UUID = Field(foreign_key="incidents.incident_id")
    # Grouping key for a batch generate request. No Batch table — batch status
    # is derived on the fly from the Form rows sharing this id.
    batch_id: UUID | None = None
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


class TemplateUpload(SQLModel, table=True):
    """A blank PDF uploaded for template authoring, plus its detection draft.

    The PDF is stored and its page geometry read synchronously, so a row exists
    with `page_count`/`pages` filled before detection starts. `status` tracks
    detection alone: a failed detection still leaves a usable upload, the user
    just draws every box by hand. Rows are drafts, not templates. Registering a
    template copies the edited fields into `form_templates` and keeps only the
    `pdf_template_ref` pointing back here.
    """

    __tablename__ = "template_uploads"

    upload_id: UUID = Field(default_factory=uuid4, primary_key=True)
    status: DetectionStatus = Field(
        default=DetectionStatus.processing, sa_column=Column(AutoString, nullable=False)
    )
    # Path on disk, and the DATA_DIR-relative reference handed to clients.
    pdf_path: str
    pdf_template_ref: str
    original_filename: str | None = None
    page_count: int = Field(default=0)
    # List of {page, width, height} in PDF points.
    pages: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    # List of DraftField objects (see app/api/schemas/templates.py).
    detected_fields: list | None = Field(default=None, sa_column=Column(JSON))
    detection_error: str | None = None
    job_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FormTemplate(SQLModel, table=True):
    """Contract Layer 6 form template registry (path/templates.yaml).

    Distinct from the legacy prototype `Template` (int PK + uploaded PDF): this
    is the standards registry keyed by `form_type`, holding incident-schema field
    definitions plus their visual `layout`. `field_count` and `last_updated` are
    derived in the response schemas (len(fields) / updated_at.date()), not stored.
    """

    __tablename__ = "form_templates"

    template_id: UUID = Field(default_factory=uuid4, primary_key=True)
    form_type: str = Field(sa_column=Column(AutoString, nullable=False, unique=True, index=True))
    display_name: str
    jurisdiction: str | None = None
    agency_type: str | None = None
    # List of TemplateField objects (see app/api/schemas/templates.py).
    fields: list = Field(sa_column=Column(JSON, nullable=False))
    source_standard: str | None = None
    pdf_template_ref: str | None = None
    version: str = Field(default="1.0")
    status: TemplateStatus = Field(
        default=TemplateStatus.active, sa_column=Column(AutoString, nullable=False)
    )
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