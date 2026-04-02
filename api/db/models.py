from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON
from typing import Optional
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


class FormFieldCoordinates(SQLModel, table=True):
    """
    Stores visual field positions detected by the vision model for a given template.
    Coordinates are stored as percentages (0-100) of the page dimensions.
    """
    id: int | None = Field(default=None, primary_key=True)
    template_id: int = Field(foreign_key="template.id", index=True)
    field_label: str                        # e.g. "patient_name", "incident_date"
    page_number: int = Field(default=0)     # 0-indexed PDF page
    x: float                                # % from left edge (0–100)
    y: float                                # % from top edge (0–100)
    width: float                            # % of page width
    height: float                           # % of page height
    field_type: str = Field(default="text") # "text", "checkbox", "image"
    scanned_at: datetime = Field(default_factory=datetime.utcnow)