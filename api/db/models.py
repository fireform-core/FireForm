from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON
from datetime import datetime
from typing import Optional


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
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    device_id: Optional[str] = None
    officer_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)