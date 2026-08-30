import re
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.schemas.enums import (
    DetectionStatus,
    FieldSource,
    TemplateFieldType,
    TemplateStatus,
    TextAlign,
)

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_FORM_TYPE = re.compile(r"^[a-z0-9_-]+$")


# ---------------------------------------------------------------------------
# Contract Layer 6 schemas (contracts/schemas/template-record.yaml)
# ---------------------------------------------------------------------------
class TemplateFieldLayout(BaseModel):
    """Visual placement of a field on the PDF (schemas/template-record.yaml#/TemplateFieldLayout).

    Coordinates are PDF points with the origin at the bottom-left of the page:
    box = start (x, y) .. end (x + width, y + height).
    """

    page: int = Field(ge=0, description="Zero-based page index")
    x: float = Field(ge=0, description="Lower-left X in PDF points")
    y: float = Field(ge=0, description="Lower-left Y in PDF points (origin bottom-left)")
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    font: str = "Helvetica"
    font_size: float = Field(default=10, gt=0)
    color: str = "#000000"
    align: TextAlign = TextAlign.left

    @field_validator("font")
    @classmethod
    def _font_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("font must not be blank")
        return v

    @field_validator("color")
    @classmethod
    def _color_is_hex(cls, v: str) -> str:
        if not _HEX_COLOR.match(v):
            raise ValueError('color must be a hex string like "#000000"')
        return v


class TemplateField(BaseModel):
    """One field definition within a template (schemas/template-record.yaml#/TemplateField).

    `source` decides where the value comes from, and each source brings its own
    requirement: schema needs an `incident_mapping`, static needs `static_text`,
    open needs a `description` (it is the instruction the extractor is given),
    and manual needs neither. `layout` places the box on the PDF.
    """

    field_name: str
    field_type: TemplateFieldType
    source: FieldSource
    required: bool
    description: str | None = None
    max_length: int | None = Field(default=None, gt=0)
    # No bound on min/max themselves: contract values legitimately go negative
    # (temperatures, elevations). Only their order is checked below.
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[str] | None = None
    incident_mapping: str | None = None
    static_text: str | None = None
    default_value: object | None = None
    unit: str | None = None
    layout: TemplateFieldLayout | None = None

    @field_validator("field_name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("field_name must not be empty")
        return v

    @model_validator(mode="after")
    def _check_field(self) -> "TemplateField":
        has_mapping = bool(self.incident_mapping and self.incident_mapping.strip())
        has_static = self.static_text is not None
        has_description = bool(self.description and self.description.strip())

        if self.source is FieldSource.schema and not has_mapping:
            raise ValueError(
                f"field '{self.field_name}': incident_mapping is required when source is 'schema'"
            )
        if self.source is not FieldSource.schema and has_mapping:
            raise ValueError(
                f"field '{self.field_name}': incident_mapping is only allowed when source is 'schema'"
            )
        if self.source is FieldSource.static and not has_static:
            raise ValueError(
                f"field '{self.field_name}': static_text is required when source is 'static'"
            )
        if self.source is not FieldSource.static and has_static:
            raise ValueError(
                f"field '{self.field_name}': static_text is only allowed when source is 'static'"
            )
        if self.source is FieldSource.open and not has_description:
            raise ValueError(
                f"field '{self.field_name}': description is required when source is 'open'. "
                "It is the instruction the extractor is given."
            )
        if self.field_type == TemplateFieldType.enum and not self.allowed_values:
            raise ValueError(
                f"field '{self.field_name}': allowed_values is required when field_type is 'enum'"
            )
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise ValueError(
                f"field '{self.field_name}': min_value must be <= max_value"
            )
        return self


class CreateTemplateRequest(BaseModel):
    """POST/PUT request body (schemas/template-record.yaml#/CreateTemplateRequest)."""

    form_type: str
    display_name: str
    jurisdiction: str | None = None
    agency_type: str | None = None
    fields: list[TemplateField] = Field(min_length=1)
    source_standard: str | None = None
    pdf_template_ref: str | None = None

    @field_validator("form_type")
    @classmethod
    def _form_type_slug(cls, v: str) -> str:
        v = v.strip()
        if not _FORM_TYPE.match(v):
            raise ValueError(
                "form_type must contain only lowercase letters, digits, underscores or hyphens"
            )
        return v

    @field_validator("display_name")
    @classmethod
    def _display_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("display_name must not be empty")
        return v

    @model_validator(mode="after")
    def _unique_field_names(self) -> "CreateTemplateRequest":
        names = [f.field_name for f in self.fields]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"duplicate field_name(s): {', '.join(dupes)}")
        return self


class TemplateSummary(BaseModel):
    """List item (schemas/template-record.yaml#/TemplateSummary)."""

    template_id: UUID
    form_type: str
    display_name: str
    jurisdiction: str | None = None
    agency_type: str | None = None
    version: str
    last_updated: date
    field_count: int
    status: TemplateStatus


class TemplateDetail(CreateTemplateRequest):
    """Full template definition (schemas/template-record.yaml#/Template).

    Server-generated fields layered on top of CreateTemplateRequest.
    """

    template_id: UUID
    version: str
    last_updated: date
    field_count: int
    status: TemplateStatus
    created_at: datetime
    updated_at: datetime


class TemplateFieldsResponse(BaseModel):
    """GET /templates/{id}/fields response (path/templates.yaml#/template_fields)."""

    template_id: UUID
    form_type: str
    total_fields: int
    required_fields: int
    optional_fields: int
    fields: list[TemplateField]


# ---------------------------------------------------------------------------
# PDF upload and field detection (path/templates.yaml#/templates_pdf)
# ---------------------------------------------------------------------------
class PageGeometry(BaseModel):
    """One page's size in PDF points, the unit every layout box uses."""

    page: int = Field(ge=0, description="Zero-based page index")
    width: float
    height: float


class MappingSuggestion(BaseModel):
    """One ranked incident-contract mapping guess for a detected box."""

    path: str
    label: str | None = None
    field_type: str | None = None
    section: str | None = None
    description: str | None = None
    score: float


class DraftField(BaseModel):
    """A detected box as an editable TemplateField, plus what it was guessed from."""

    field: TemplateField
    # Kept verbatim, not normalized, so the editor can show the user what the
    # suggestion was based on.
    detected_label: str | None = None
    suggestions: list[MappingSuggestion] = Field(default_factory=list)


class TemplateDraft(BaseModel):
    """Everything the visual editor needs after a PDF upload.

    The PDF is stored the moment the upload returns; only detection is async,
    so `status` describes detection alone. A failed detection still leaves a
    usable upload, the user just draws every box by hand.
    """

    upload_id: UUID
    status: DetectionStatus
    pdf_template_ref: str
    original_filename: str | None = None
    page_count: int
    pages: list[PageGeometry]
    detected_fields: list[DraftField] | None = None
    detection_error: str | None = None
    retry_after_seconds: int | None = None


class TemplateDraftAccepted(TemplateDraft):
    """202 body of POST /templates/pdf: the draft plus where to poll it.

    `job_id` is absent when detection was skipped, since there is no background
    work to follow. `poll_url` still resolves, it just answers straight away.
    """

    job_id: str | None = None
    poll_url: str
