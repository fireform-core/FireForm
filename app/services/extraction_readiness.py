"""Read-side check of an extraction against the templates that could be filled.

Once extraction finishes, the responder still has to pick a form. That choice
only makes sense if the screen can say which forms are fillable right now and
what is missing on the ones that are not. Both endpoints answer that from
stored data: one template at a time (validate) or every active template at once
(readiness). No LLM, so it stays cheap to refetch after every correction.

Plain dicts and repository calls only, no FastAPI. The route stays thin.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.api.schemas.enums import FieldSource, TemplateStatus
from app.api.schemas.extraction import (
    FieldGap,
    ReadinessMatrix,
    TemplateReadiness,
    ValidationResult,
)
from app.api.schemas.templates import TemplateField
from app.models import Extraction, FormTemplate, Incident
from app.services.extraction_review import value_at

# Open mapping on the contract. Manual and open template fields live here, and
# the extractor writes them under a single flat key, "{form_type}.{field_name}",
# rather than as nested objects.
CUSTOM_FIELDS = "custom_fields"


def is_filled(value: Any) -> bool:
    """True when the value would actually print something on the form.

    A null, a blank string and an empty container are all a blank box to the
    responder, so none of them close a gap.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def custom_key(field: TemplateField, form_type: str) -> str:
    """The custom_fields key a manual or open field is stored under."""
    return f"{form_type}.{field.field_name}"


def resolve(contract: dict, field: TemplateField, form_type: str) -> Any:
    """The value a template field would be filled with, or None.

    Where to look depends on the field's source. A schema field reads the
    contract path it declares. A static field carries its own text. Manual and
    open fields sit under custom_fields, which is a flat mapping: the dotted
    key is one key, not a path, so it is read directly instead of walked.
    """
    if field.source is FieldSource.static:
        return field.static_text
    if field.source is FieldSource.schema:
        return value_at(contract, field.incident_mapping or "")

    custom = contract.get(CUSTOM_FIELDS)
    if not isinstance(custom, dict):
        return None
    return custom.get(custom_key(field, form_type))


def mapping_of(field: TemplateField, form_type: str) -> str | None:
    """What to show the UI as the origin of a missing value.

    A schema field points at the contract path to correct. A manual or open
    field points at the custom_fields key the typed value goes into.
    """
    if field.source is FieldSource.schema:
        return field.incident_mapping
    if field.source is FieldSource.static:
        return None
    return f"{CUSTOM_FIELDS}.{custom_key(field, form_type)}"


def _gap(field: TemplateField, form_type: str) -> FieldGap:
    return FieldGap(
        field_name=field.field_name,
        source=field.source,
        incident_mapping=mapping_of(field, form_type),
        description=field.description,
    )


def _parse_fields(template: FormTemplate) -> list[TemplateField]:
    """The template's stored field definitions as models."""
    return [TemplateField.model_validate(entry) for entry in template.fields or []]


def warnings_for(gaps: list[FieldGap]) -> list[str]:
    """One readable line per recommended field that has no value.

    Built from the gaps themselves rather than a rule table per form type, so
    a newly registered template gets useful warnings without anyone adding to
    a list first.
    """
    lines = []
    for gap in gaps:
        where = gap.incident_mapping or gap.field_name
        line = f"{where} has no value. '{gap.field_name}' is optional on this form"
        if gap.description:
            line = f"{line}: {gap.description}"
        lines.append(line)
    return lines


@dataclass(frozen=True)
class Gaps:
    """What one template is missing, and how much of it is filled."""

    missing_required: list[FieldGap]
    missing_recommended: list[FieldGap]
    coverage_percent: float

    @property
    def ready(self) -> bool:
        return not self.missing_required


def gaps_for(contract: dict, template: FormTemplate) -> Gaps:
    """Compare a contract document against one template's field list."""
    fields = _parse_fields(template)
    missing_required: list[FieldGap] = []
    missing_recommended: list[FieldGap] = []
    filled = 0

    for field in fields:
        if is_filled(resolve(contract, field, template.form_type)):
            filled += 1
            continue
        gap = _gap(field, template.form_type)
        if field.required:
            missing_required.append(gap)
        else:
            missing_recommended.append(gap)

    coverage = round(filled / len(fields) * 100, 1) if fields else 0.0
    return Gaps(missing_required, missing_recommended, coverage)


def validate_template(
    extraction: Extraction, incident: Incident, template: FormTemplate
) -> ValidationResult:
    """The single-template answer: can this form be generated right now."""
    gaps = gaps_for(incident.incident_contract or {}, template)
    return ValidationResult(
        valid=gaps.ready,
        template_id=template.template_id,
        extract_id=extraction.extract_id,
        form_type=template.form_type,
        missing_required=gaps.missing_required,
        missing_recommended=gaps.missing_recommended,
        warnings=warnings_for(gaps.missing_recommended),
        field_coverage_percent=gaps.coverage_percent,
    )


def readiness_matrix(
    extraction: Extraction, incident: Incident, templates: list[FormTemplate]
) -> ReadinessMatrix:
    """The same check across every active template, for the selection screen.

    Drafts and legacy templates are left out: nothing on the selection screen
    should offer a form that is not in service.
    """
    contract = incident.incident_contract or {}
    rows = []
    for template in templates:
        if template.status != TemplateStatus.active:
            continue
        gaps = gaps_for(contract, template)
        rows.append(
            TemplateReadiness(
                template_id=template.template_id,
                form_type=template.form_type,
                display_name=template.display_name,
                ready=gaps.ready,
                missing_required=gaps.missing_required,
                missing_recommended=gaps.missing_recommended,
                field_coverage_percent=gaps.coverage_percent,
            )
        )
    return ReadinessMatrix(
        extract_id=extraction.extract_id,
        templates=rows,
        computed_at=datetime.now(timezone.utc),
    )


__all__ = [
    "Gaps",
    "gaps_for",
    "is_filled",
    "readiness_matrix",
    "resolve",
    "validate_template",
    "warnings_for",
]
