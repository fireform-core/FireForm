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