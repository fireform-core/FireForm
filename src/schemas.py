import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator, ValidationInfo

class IncidentType(str, Enum):
    FIRE = "FIRE"
    RESCUE = "RESCUE"
    MEDICAL = "MEDICAL"
    HAZMAT = "HAZMAT"
    OTHER = "OTHER"

class ConfidenceScore(BaseModel):
    """Tracks LLM extraction confidence for heatmaps and human review requirements."""
    field_name: str
    score: float = Field(ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    human_review_needed: bool

class SpatialData(BaseModel):
    address: str = Field(description="Address or descriptive location of the incident.", min_length=1)
    coordinates: Tuple[float, float] = Field(description="Approximate latitude and longitude coordinates.")

class MedicalData(BaseModel):
    injuries: bool = Field(description="Were there any injuries?")
    severity: str = Field(description="Description of the injury severity (e.g., minor, critical, fatal).")

class OperationalData(BaseModel):
    units_responding: List[str] = Field(description="List of units that responded (e.g., Engine 1, Ladder 2).", min_length=1)
    incident_type: IncidentType = Field(description="Primary type of incident.")

class IncidentReport(BaseModel):
    """
    Standard NFIRS-aligned Incident Report.
    Strict Pydantic model enforcing critical business rules.
    """
    incident_id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique identifier for the incident.")
    timestamp: datetime = Field(description="Time of the incident in ISO format.", default_factory=lambda: datetime.now(timezone.utc))
    narrative: str = Field(description="Summary narrative of the event.", min_length=10)
    
    # Aggregated Sub-Schemas for Pareto Extraction
    spatial: SpatialData
    medical: MedicalData
    operational: OperationalData

    # Note: the extraction process can attach confidence scores per field.
    confidence_scores: Optional[List[ConfidenceScore]] = Field(default=None, description="Model confidence per extracted field.")

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp_past(cls, v: datetime, info: ValidationInfo) -> datetime:
        """Ensure the timestamp is not in the future."""
        # Convert both to UTC for comparison if necessary
        now = datetime.now(timezone.utc)
        if getattr(v, "tzinfo", None) is None:
            v = v.replace(tzinfo=timezone.utc)
        if v > now:
            raise ValueError(f"Incident timestamp {v} cannot be in the future.")
        return v
