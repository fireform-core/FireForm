"""Review-screen write path for an extraction.

A responder fixes a wrong value, adds a missing one or drops one the model
invented. The correction arrives as a JSON Merge Patch (RFC 7396) shaped like
the incident contract, and this module applies it to the contract document on
the linked incident row, which is the single store of incident data.

Everything here works on plain dicts and repository calls, no FastAPI. The
route stays a thin handler.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import UnionType
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from app.api.schemas.enums import ExtractionStatus, ReportStatus
from app.api.schemas.incident_contract import IncidentContract
from app.core.errors.base import AppError, ValidationAppError
from app.db.repositories import update_extraction, update_incident
from app.models import Extraction, Incident
from app.services.incidents import promote

# Deleting a key is the whole point of RFC 7396, so a null in the patch is a
# delete, never a value. Kept as a name so the intent reads at the call sites.
DELETE = None


# ---------------------------------------------------------------------------
# RFC 7396 merge patch
# ---------------------------------------------------------------------------

def merge_patch(target: Any, patch: Any) -> Any:
    """Apply a JSON Merge Patch to a document (RFC 7396).

    A non-object patch replaces the target outright. Inside an object, a null
    removes the key, a nested object merges recursively, anything else
    replaces.
    """
    if not isinstance(patch, dict):
        return patch

    result = dict(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is DELETE:
            result.pop(key, None)
        else:
            result[key] = merge_patch(result.get(key), value)
    return result


def patch_paths(patch: dict, prefix: str = "") -> list[tuple[str, Any]]:
    """Every leaf of the patch as a (dotted path, value) pair.

    Nested objects are walked so a patch that only touches
    ``losses.property_loss.amount`` records that one path and not its parents.
    A list, a scalar and an empty object are leaves: the merge replaces them
    whole, so that is the level a correction is recorded at.
    """
    leaves: list[tuple[str, Any]] = []
    for key, value in patch.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and value:
            leaves.extend(patch_paths(value, path))
        else:
            leaves.append((path, value))
    return leaves


def value_at(document: Any, path: str) -> Any:
    """Value at a dotted path, or None when any step is missing."""
    current = document
    for key in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


# ---------------------------------------------------------------------------
# Field path checking
# ---------------------------------------------------------------------------

def _model_of(annotation: Any) -> type[BaseModel] | None:
    """The contract submodel behind an annotation, or None.

    Generated fields are Optional and sometimes list-valued. A list is not
    walked into (a patch replaces the whole list), so only a plain object
    annotation yields a model.
    """
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        for arg in get_args(annotation):
            if arg is type(None):
                continue
            return _model_of(arg)
        return None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _is_open_mapping(annotation: Any) -> bool:
    """True for a free-form object like custom_fields, whose keys are open."""
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        return any(
            _is_open_mapping(arg) for arg in get_args(annotation) if arg is not type(None)
        )
    return origin is dict


def unknown_paths(patch: dict, model: type[BaseModel], prefix: str = "") -> list[str]:
    """Dotted paths in the patch that the contract has no field for.

    The generated models ignore unknown keys, so without this check a typo
    would be accepted and then silently dropped on the way to the database.
    Open mappings such as custom_fields accept any key by design.
    """
    unknown: list[str] = []
    for key, value in patch.items():
        path = f"{prefix}.{key}" if prefix else key
        field = model.model_fields.get(key)
        if field is None:
            unknown.append(path)
            continue
        if not isinstance(value, dict) or not value:
            continue
        if _is_open_mapping(field.annotation):
            continue
        submodel = _model_of(field.annotation)
        if submodel is not None:
            unknown.extend(unknown_paths(value, submodel, path))
    return unknown


def _validation_errors(exc: ValidationError) -> list[dict]:
    """Pydantic errors as the contract's validation_errors entries."""
    errors = []
    for error in exc.errors():
        path = ".".join(str(part) for part in error.get("loc", ()))
        errors.append({
            "field": path or None,
            "issue": error.get("msg"),
            "value": error.get("input"),
        })
    return errors


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------

def correction_entries(
    patch: dict,
    before: dict,
    after: dict,
    corrected_at: datetime,
    corrected_by: str | None = None,
) -> list[dict]:
    """Audit entries for the paths the patch actually changed.

    A path whose value is the same before and after is a no-op and is not
    recorded, so the trail stays a history of real edits.
    """
    entries = []
    for path, _ in patch_paths(patch):
        original = value_at(before, path)
        corrected = value_at(after, path)
        if original == corrected:
            continue
        entries.append({
            "field_path": path,
            "original_value": original,
            "corrected_value": corrected,
            "corrected_at": corrected_at.isoformat(),
            "corrected_by": corrected_by,
        })
    return entries


class ExtractionReviewService:
    """Applies manual corrections to a completed extraction."""

    def apply_patch(
        self,
        session: Session,
        extraction: Extraction,
        incident: Incident,
        patch: dict,
        corrected_by: str | None = None,
    ) -> tuple[Extraction, Incident]:
        """Merge the patch into the contract, then rewrite everything derived.

        The document, the promoted analytics columns and the corrections trail
        all move together in one call so they can never disagree.
        """
        self._reject_locked(incident)
        self._reject_unknown_paths(patch)

        before = incident.incident_contract or {}
        merged = merge_patch(before, patch)
        after = self._validated(merged)

        now = datetime.now(timezone.utc)
        entries = correction_entries(patch, before, after, now, corrected_by)

        incident.incident_contract = after
        for column, value in promote(after).items():
            setattr(incident, column, value)
        incident.updated_at = now
        incident = update_incident(session, incident)

        if entries:
            # Reassign rather than append: SQLModel tracks JSON columns by
            # identity, so mutating the list in place would not be persisted.
            extraction.corrections = (extraction.corrections or []) + entries
            extraction.updated_at = now
            extraction = update_extraction(session, extraction)

        return extraction, incident

    def _reject_locked(self, incident: Incident) -> None:
        if incident.status == ReportStatus.submitted:
            raise AppError(
                "Cannot modify extraction incident report has been submitted",
                status_code=409,
                error_code="EXTRACT_LOCKED",
                detail={
                    "report_status": incident.status,
                    "submitted_at": incident.updated_at.isoformat()
                    if incident.updated_at
                    else None,
                },
            )

    def _reject_unknown_paths(self, patch: dict) -> None:
        unknown = unknown_paths(patch, IncidentContract)
        if unknown:
            raise ValidationAppError(
                "Invalid field path or value in patch",
                validation_errors=[
                    {
                        "field": path,
                        "issue": "Unknown field path in the incident contract",
                        "value": value_at(patch, path),
                    }
                    for path in unknown
                ],
            )

    def _validated(self, merged: dict) -> dict:
        """Validate the merged document and return it normalized.

        Dumping the validated model back out is what strips the keys a delete
        removed and settles types (dates, enums) into their JSON form, so the
        stored document always matches the contract.
        """
        try:
            model = IncidentContract.model_validate(merged)
        except ValidationError as exc:
            raise ValidationAppError(
                "Invalid field path or value in patch",
                validation_errors=_validation_errors(exc),
            ) from exc
        return model.model_dump(mode="json", exclude_none=True)


def load_for_review(extraction: Extraction, incident: Incident | None) -> Incident:
    """The incident row a correction writes to, or the reason there is none.

    An extraction that has not completed has no contract document yet, so
    there is nothing to correct.
    """
    if extraction.status != ExtractionStatus.completed or incident is None:
        raise AppError(
            f"Extraction is in '{extraction.status}' state. Wait until status is 'completed'.",
            status_code=409,
            error_code="EXTRACT_NOT_COMPLETED",
            detail={"current_status": extraction.status},
        )
    return incident


__all__ = [
    "ExtractionReviewService",
    "correction_entries",
    "load_for_review",
    "merge_patch",
    "patch_paths",
    "unknown_paths",
    "value_at",
]
