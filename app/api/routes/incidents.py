"""Contract Layer 4 incident endpoints (contracts/path/incidents.yaml).

Handlers are thin; the logic lives in app/services/incident_crud.py. The one
job kept here is assembling the response shapes, since the DB stores the
promoted analytics as flat columns while the contract nests them under
`analytics`.
"""

from datetime import date
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.deps import get_db
from app.api.schemas.common import Pagination
from app.api.schemas.enums import IncidentCategory, ReportStatus
from app.api.schemas.form_generation import FormRecord
from app.api.schemas.incidents import (
    CreateIncidentRequest,
    DeleteIncidentResponse,
    GeneratedForm,
    IncidentAnalytics,
    IncidentListItem,
    IncidentListResponse,
    IncidentRecord,
    IncidentRecordFull,
    SubmissionLogEntry,
    UpdateIncidentRequest,
)
from app.api.schemas.incident_contract import IncidentContract
from app.models import Form, Incident
from app.services.incident_crud import IncidentService

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _form_summary(form: Form) -> GeneratedForm:
    return GeneratedForm(form_id=form.form_id, form_type=form.form_type, status=form.status)


def _record(incident: Incident, forms: list[Form]) -> IncidentRecord:
    """The incident row as the contract's IncidentRecord."""
    return IncidentRecord(
        incident_id=incident.incident_id,
        extract_id=incident.extract_id,
        incident_number=incident.incident_number,
        status=incident.status,
        incident_name=incident.incident_name,
        incident_type=incident.incident_type,
        incident_category=incident.incident_category,
        incident_datetime=incident.incident_datetime,
        analytics=IncidentAnalytics.model_validate(incident),
        forms_generated=[_form_summary(f) for f in forms],
        tags=incident.tags or [],
        notes=incident.notes,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        deleted_at=incident.deleted_at,
    )


def _submission_log(contract: dict | None) -> list[SubmissionLogEntry]:
    """Submissions read out of the contract document.

    Empty until the submission layer exists; nothing writes it today.
    """
    entries = (contract or {}).get("submission_log")
    if not isinstance(entries, list):
        return []
    return [SubmissionLogEntry.model_validate(e) for e in entries if isinstance(e, dict)]


@router.post("", response_model=IncidentRecord, status_code=201)
def create_incident(body: CreateIncidentRequest, db: Session = Depends(get_db)):
    service = IncidentService()
    incident = service.finalize(db, body)
    return _record(incident, service.forms(db, incident.incident_id))


@router.get("", response_model=IncidentListResponse)
def list_incidents(
    db: Session = Depends(get_db),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    incident_category: IncidentCategory | None = Query(default=None),
    status: ReportStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="date_desc", pattern="^(date_asc|date_desc)$"),
):
    rows, counts, total = IncidentService().list_page(
        db,
        date_from=date_from,
        date_to=date_to,
        incident_category=incident_category,
        status=status,
        page=page,
        per_page=per_page,
        sort=sort,
    )
    total_pages = ceil(total / per_page) if total else 0
    return IncidentListResponse(
        data=[
            IncidentListItem(
                incident_id=row.incident_id,
                incident_number=row.incident_number,
                status=row.status,
                incident_name=row.incident_name,
                incident_type=row.incident_type,
                incident_category=row.incident_category,
                incident_datetime=row.incident_datetime,
                city=row.city,
                country=row.country,
                forms_count=counts.get(row.incident_id, 0),
                created_at=row.created_at,
            )
            for row in rows
        ],
        pagination=Pagination(
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )


@router.get("/{incident_id}", response_model=IncidentRecordFull)
def get_incident(incident_id: UUID, db: Session = Depends(get_db)):
    service = IncidentService()
    incident = service.get(db, incident_id)
    forms = service.forms(db, incident_id)
    base = _record(incident, forms)
    return IncidentRecordFull(
        **base.model_dump(),
        incident_contract=(
            IncidentContract.model_validate(incident.incident_contract)
            if incident.incident_contract
            else None
        ),
        forms=[FormRecord.model_validate(f, from_attributes=True) for f in forms],
        submission_log=_submission_log(incident.incident_contract),
    )


@router.patch("/{incident_id}", response_model=IncidentRecord)
def update_incident(
    incident_id: UUID, body: UpdateIncidentRequest, db: Session = Depends(get_db)
):
    service = IncidentService()
    incident = service.update(db, incident_id, body)
    return _record(incident, service.forms(db, incident_id))


@router.delete("/{incident_id}", response_model=DeleteIncidentResponse)
def delete_incident(incident_id: UUID, db: Session = Depends(get_db)):
    incident = IncidentService().soft_delete(db, incident_id)
    return DeleteIncidentResponse(
        incident_id=incident.incident_id,
        deleted_at=incident.deleted_at,
    )
