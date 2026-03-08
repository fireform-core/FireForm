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
    output_pdf_path: str
    # BCP-47 language code detected from the raw input (e.g. "fr", "ar", "en")
    detected_language: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)