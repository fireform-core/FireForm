from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON
from datetime import datetime

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
    output_pdf_path: str | None = None
    status: str = Field(default="incomplete")
    required_completion_pct: int = Field(default=0)
    completed_required_fields: list = Field(default_factory=list, sa_column=Column(JSON))
    missing_required_fields: list = Field(default_factory=list, sa_column=Column(JSON))
    attempts_used: int = Field(default=1)
    retry_prompt: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)