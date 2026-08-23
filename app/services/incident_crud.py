"""Contract Layer 4 incident CRUD (contracts/path/incidents.yaml).

Read/write operations on the incident row itself. The promoted analytics
columns are not touched here: they are derived from the contract document by
`app.services.incidents.promote`, which runs on the extraction path and on
PATCH /extract. This module only moves the metadata a user owns, so the two
can never fight over the same column.
"""

from datetime import date, datetime, timezone
from uuid import UUID

from sqlmodel import Session

from app.api.schemas.enums import IncidentCategory, ReportStatus
from app.api.schemas.incidents import CreateIncidentRequest, UpdateIncidentRequest
from app.core.errors.base import AppError
from app.db.repositories import (
    count_forms_by_incident,
    get_extraction,
    get_incident,
    get_incident_by_extract,
    get_incident_by_number,
    list_forms_by_incident,
    list_incidents,
    update_incident,
)
from app.models import Form, Incident


def _now() -> datetime:
    return datetime.now(timezone.utc)


class IncidentService:
    """Business logic for the five incident endpoints."""

    def finalize(self, session: Session, body: CreateIncidentRequest) -> Incident:
        """POST /incidents: finalize the draft created when extraction completed.

        Never creates a second row. Calling it again for the same extraction
        just reapplies the number and tags, so a client that retries after a
        dropped response gets the same incident back.
        """
        incident = get_incident_by_extract(session, body.extract_id)
        if incident is None:
            # Distinguish "no such extraction" from "extraction exists but has
            # not produced its draft yet", because only the second is worth
            # retrying.
            if get_extraction(session, body.extract_id) is None:
                raise AppError(
                    f"Extract {body.extract_id} not found",
                    status_code=404,
                    error_code="EXTRACT_NOT_FOUND",
                )
            raise AppError(
                "Extraction has not completed yet, so it has no incident to finalize",
                status_code=409,
                error_code="EXTRACTION_NOT_COMPLETED",
                detail={"extract_id": str(body.extract_id)},
            )

        if body.incident_number is not None:
            self._require_number_free(session, body.incident_number, incident.incident_id)
            incident.incident_number = body.incident_number
        if body.tags is not None:
            incident.tags = body.tags

        incident.updated_at = _now()
        return update_incident(session, incident)

    def get(self, session: Session, incident_id: UUID) -> Incident:
        """A single incident, soft-deleted ones included.

        Reads stay open on a deleted incident: the DELETE response promises the
        row is recoverable, which is meaningless if it cannot be read back.
        """
        incident = get_incident(session, incident_id)
        if incident is None:
            raise AppError(
                f"Incident {incident_id} not found",
                status_code=404,
                error_code="INCIDENT_NOT_FOUND",
            )
        return incident

    # Not named `list`: that would shadow the builtin for the rest of the class
    # body, breaking every later `list[...]` annotation.
    def list_page(
        self,
        session: Session,
        date_from: date | None = None,
        date_to: date | None = None,
        incident_category: IncidentCategory | None = None,
        status: ReportStatus | None = None,
        page: int = 1,
        per_page: int = 20,
        sort: str = "date_desc",
    ) -> tuple[list[Incident], dict[UUID, int], int]:
        """One page of live incidents, their form counts, and the total."""
        if date_from is not None and date_to is not None and date_from > date_to:
            raise AppError(
                "date_from must not be later than date_to",
                status_code=422,
                error_code="VALIDATION_ERROR",
                detail={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
            )

        rows, total = list_incidents(
            session,
            date_from=date_from,
            date_to=date_to,
            incident_category=incident_category,
            status=status,
            page=page,
            per_page=per_page,
            sort=sort,
        )
        counts = count_forms_by_incident(session, [row.incident_id for row in rows])
        return rows, counts, total

    def forms(self, session: Session, incident_id: UUID) -> list[Form]:
        return list_forms_by_incident(session, incident_id)

    def update(
        self, session: Session, incident_id: UUID, body: UpdateIncidentRequest
    ) -> Incident:
        """PATCH /incidents/{id}: update the metadata a user owns.

        Only fields present in the request body are applied, so omitting one
        leaves it alone rather than clearing it. The contract document and the
        columns promoted from it are untouched; correcting those is PATCH
        /extract.
        """
        incident = self.get(session, incident_id)
        changes = body.model_dump(exclude_unset=True)

        if "incident_number" in changes and changes["incident_number"] is not None:
            self._require_number_free(session, changes["incident_number"], incident_id)

        for field, value in changes.items():
            setattr(incident, field, value)

        incident.updated_at = _now()
        return update_incident(session, incident)

    def soft_delete(self, session: Session, incident_id: UUID) -> Incident:
        """DELETE /incidents/{id}: stamp deleted_at. Data is never removed."""
        incident = self.get(session, incident_id)
        if incident.deleted_at is not None:
            raise AppError(
                "Incident has already been deleted",
                status_code=409,
                error_code="ALREADY_DELETED",
                detail={"deleted_at": incident.deleted_at.isoformat()},
            )

        incident.deleted_at = _now()
        incident.updated_at = incident.deleted_at
        return update_incident(session, incident)

    def _require_number_free(
        self, session: Session, incident_number: str, incident_id: UUID
    ) -> None:
        """Reject a number already held by a different live incident."""
        existing = get_incident_by_number(session, incident_number)
        if existing is not None and existing.incident_id != incident_id:
            raise AppError(
                f"Incident number {incident_number} already exists",
                status_code=409,
                error_code="DUPLICATE_INCIDENT_NUMBER",
                detail={"existing_incident_id": str(existing.incident_id)},
            )
