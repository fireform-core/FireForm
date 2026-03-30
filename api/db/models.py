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
    created_at: datetime = Field(default_factory=datetime.utcnow)

# ADD THIS TO api/db/models.py
# (append to existing file — don't replace)

from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class IncidentMasterData(SQLModel, table=True):
    """
    The Incident Data Lake.
    Stores all extracted data from one incident as a master JSON blob.
    Any agency can generate their PDF from this single record — zero new LLM calls.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    incident_id: str = Field(index=True)        # INC-2026-0321-4821
    master_json: str                             # JSON string — all extracted fields
    transcript_text: str                         # original transcript
    location_lat: Optional[float] = None        # from PWA GPS
    location_lng: Optional[float] = None        # from PWA GPS
    officer_notes: Optional[str] = None         # additional context
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)