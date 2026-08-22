"""Contract Layer 4 incident schemas (contracts/schemas/incident-record.yaml).

The DB stores the promoted analytics as flat columns on the incident row, but
the contract nests them under an `analytics` object. `IncidentAnalytics` owns
that reshaping so routes and services never assemble the block by hand.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.common import Pagination
from app.api.schemas.enums import FormStatus, IncidentCategory, ReportStatus
from app.api.schemas.form_generation import FormRecord
from app.api.schemas.incident_contract import IncidentContract


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class CreateIncidentRequest(BaseModel):
    """POST /incidents body.

    Finalizes the draft incident that was created when the extraction
    completed. `extract_id` resolves to that existing row; a second row is
    never created for the same extraction.
    """

    extract_id: UUID
    incident_number: str | None = None
    tags: list[str] | None = None


class UpdateIncidentRequest(BaseModel):
    """PATCH /incidents/{id} body.

    A partial update: only the fields actually present in the request body are
    applied, so omitting a field leaves it untouched rather than nulling it.
    Callers read that distinction off `model_fields_set`, which is why no
    field here carries a meaningful default.
    """

    status: ReportStatus | None = None
    tags: list[str] | None = None
    incident_number: str | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class IncidentAnalytics(BaseModel):
    """Read-only stats promoted out of the incident contract.

    Recomputed server-side by `app.services.incidents.promote` on every change
    to the document. Clients never write these.
    """

    model_config = ConfigDict(from_attributes=True)

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


class GeneratedForm(BaseModel):
    """One entry in `forms_generated`, the at-a-glance form summary."""

    form_id: UUID
    # Open string rather than the FormType enum, matching FormRecord: a
    # registry can hold form types the closed enum does not know about yet.
    form_type: str
    status: FormStatus


class IncidentRecord(BaseModel):
    """The incident record without its contract document or full form rows."""

    incident_id: UUID
    extract_id: UUID
    incident_number: str | None = None
    status: ReportStatus
    incident_name: str | None = None
    incident_type: str | None = None
    incident_category: IncidentCategory | None = None
    incident_datetime: datetime | None = None
    analytics: IncidentAnalytics | None = None
    forms_generated: list[GeneratedForm] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class SubmissionLogEntry(BaseModel):
    """One agency submission, read out of the contract document.

    Stays empty until the submission layer exists; nothing writes it today.
    """

    form_type: str | None = None
    submitted_at: datetime | None = None
    submitted_to: str | None = None
    status: str | None = None


class IncidentRecordFull(IncidentRecord):
    """GET /incidents/{id}: the record plus everything hanging off it."""

    incident_contract: IncidentContract | None = None
    forms: list[FormRecord] = Field(default_factory=list)
    submission_log: list[SubmissionLogEntry] = Field(default_factory=list)


class IncidentListItem(BaseModel):
    """One row of GET /incidents.

    Deliberately flatter than IncidentRecord: a list view needs the location
    columns but not the whole analytics block, and a form count rather than
    the forms themselves.
    """

    incident_id: UUID
    incident_number: str | None = None
    status: ReportStatus
    incident_name: str | None = None
    incident_type: str | None = None
    incident_category: IncidentCategory | None = None
    incident_datetime: datetime | None = None
    city: str | None = None
    country: str | None = None
    forms_count: int = 0
    created_at: datetime


class IncidentListResponse(BaseModel):
    data: list[IncidentListItem] = Field(default_factory=list)
    pagination: Pagination


class DeleteIncidentResponse(BaseModel):
    """200 body for DELETE /incidents/{id}. The row is never removed."""

    incident_id: UUID
    deleted_at: datetime
    recoverable: bool = True
