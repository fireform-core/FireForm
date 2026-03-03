from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON
from datetime import datetime
import uuid


class Template(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    fields: dict = Field(sa_column=Column(JSON))
    pdf_path: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FormSubmission(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    template_id: int
    input_text: str
    output_pdf_path: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FillJob(SQLModel, table=True):
    """
    Tracks an asynchronous form-fill job submitted via POST /forms/fill/async.
    Clients poll GET /forms/jobs/{id} to check status and retrieve results.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    status: str = Field(default="pending")  # pending | running | complete | failed
    template_id: int
    input_text: str
    output_pdf_path: str | None = None
    partial_results: dict | None = Field(default=None, sa_column=Column(JSON))
    field_confidence: dict | None = Field(default=None, sa_column=Column(JSON))
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BatchSubmission(SQLModel, table=True):
    """
    Tracks a multi-template batch fill submitted via POST /forms/fill/batch.

    A single BatchSubmission represents one incident transcript filled into
    N agency forms simultaneously using a single canonical LLM extraction pass.
    The canonical_extraction JSON column stores the full per-field evidence
    record (value + verbatim transcript quote + confidence) for audit purposes.

    submission_ids links to the individual FormSubmission records created for
    each template so clients can retrieve per-template output PDF paths.
    errors stores per-template error messages for partial failure cases.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    status: str = Field(default="complete")  # complete | partial | failed
    input_text: str
    # Full canonical extraction: category -> {value, evidence, confidence}
    canonical_extraction: dict | None = Field(default=None, sa_column=Column(JSON))
    # Evidence report: only categories with non-null extracted values
    evidence_report: dict | None = Field(default=None, sa_column=Column(JSON))
    # List of template IDs that were requested
    template_ids: list = Field(sa_column=Column(JSON))
    # List of FormSubmission integer IDs created (one per template)
    submission_ids: list | None = Field(default=None, sa_column=Column(JSON))
    # Per-template output paths: {template_id: output_pdf_path}
    output_paths: dict | None = Field(default=None, sa_column=Column(JSON))
    # Per-template errors: {template_id: error_message} for partial failures
    errors: dict | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)