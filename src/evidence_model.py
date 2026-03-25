"""
Evidence Traceability Model

Captures field-level evidence chains showing:
- Which source provided each field value
- Which extraction method was used
- Confidence level of the match
- Timestamp of evidence capture
"""

from datetime import datetime
from typing import Any
from pydantic import BaseModel


class FieldEvidence(BaseModel):
    """Single piece of evidence for a field value."""
    
    source_id: str  # "incident_record", "template_schema", "user_input", "default"
    method: str  # "direct", "inference", "default", "inferred_alias"
    confidence: float  # 0.0 to 1.0
    timestamp: datetime
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class FieldTraceRecord(BaseModel):
    """Complete trace record for a single field."""
    
    field_name: str
    source_value: Any  # Original value from source
    final_value: Any  # Value after normalization/processing
    evidence_chain: list[FieldEvidence]  # Chain of evidence supporting this value
    
    @property
    def primary_evidence(self) -> FieldEvidence | None:
        """Return the highest confidence evidence."""
        if not self.evidence_chain:
            return None
        return max(self.evidence_chain, key=lambda e: e.confidence)


class TraceContext(BaseModel):
    """Context for a batch trace (top-level metadata)."""
    
    incident_id: str
    template_id: int
    template_name: str
    trace_start_time: datetime
    trace_end_time: datetime | None = None
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class FieldEvidenceReport(BaseModel):
    """Evidence metadata to include in mapping report."""
    
    field_name: str
    matched: bool  # True if field was found in incident record
    source_id: str  # Primary source
    method: str  # Primary method
    confidence: float  # Primary confidence
    evidence_count: int  # How many pieces of evidence support this field
    
    class Config:
        pass
