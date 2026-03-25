from pydantic import BaseModel


class FormFill(BaseModel):
    template_id: int
    input_text: str


class FormFillResponse(BaseModel):
    id: int
    template_id: int
    input_text: str
    output_pdf_path: str

    class Config:
        from_attributes = True


class FieldEvidenceMetadata(BaseModel):
    """Evidence metadata for a single field."""
    field_name: str
    matched: bool
    source_id: str
    method: str
    confidence: float
    evidence_count: int


class BatchTemplateMappingReport(BaseModel):
    compatible: bool
    missing_fields: list[str]
    extra_fields: list[str]
    unmapped_fields: list[str]
    type_mismatches: dict[str, str]
    dependency_violations: list[list[str] | tuple[str, str]]
    warnings: list[str]
    matched_fields: list[str]
    field_evidence: dict[str, FieldEvidenceMetadata] | None = None


class BatchTemplateResult(BaseModel):
    template_id: int
    template_name: str
    status: str
    output_pdf_path: str | None
    error: str | None
    mapping_report: BatchTemplateMappingReport


class FormBatchFill(BaseModel):
    template_ids: list[int]
    incident_record: dict


class FormBatchFillResponse(BaseModel):
    batch_id: str
    total_templates: int
    successful_count: int
    failed_count: int
    package_zip_path: str
    download_url: str
    results: list[BatchTemplateResult]