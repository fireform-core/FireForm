from pydantic import BaseModel
from datetime import datetime
from api.db.models import Datatype


class FormSubmissionResponse(BaseModel):
    id: int
    template_id: int
    report_schema_id: int | None
    name: str | None
    input_text: str
    output_pdf_path: str
    created_at: datetime

    class Config:
        from_attributes = True


class ReportSchemaCreate(BaseModel):
    name: str
    description: str
    use_case: str

class ReportSchemaUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    use_case: str | None = None

class TemplateAssociation(BaseModel):
    template_id: int

class ReportFill(BaseModel):
    input_text: str
    name: str | None = None

class ReportFillResponse(BaseModel):
    schema_id: int
    input_text: str
    output_pdf_paths: list[str]
    submission_ids: list[int] = []

class SchemaFieldUpdate(BaseModel):
    description: str | None = None
    data_type: Datatype | None = None
    word_limit: int | None = None
    required: bool | None = None
    allowed_values: dict | None = None
    canonical_name: str | None = None


class SchemaFieldResponse(BaseModel):
    id: int
    report_schema_id: int
    field_name: str
    source_template_id: int
    description: str
    data_type: Datatype
    word_limit: int | None
    required: bool
    allowed_values: dict | None
    canonical_name: str | None

    class Config:
        from_attributes = True

class TemplateInSchema(BaseModel):
    id: int
    template_id: int
    report_schema_id: int
    field_mapping: dict

    class Config:
        from_attributes = True

class ReportSchemaResponse(BaseModel):
    id: int
    name: str
    description: str
    use_case: str
    created_at: datetime
    templates: list[TemplateInSchema] = []
    fields: list[SchemaFieldResponse] = []

    class Config:
        from_attributes = True


class CanonicalFieldEntry(BaseModel):
    canonical_name: str
    description: str
    data_type: Datatype
    word_limit: int | None
    required: bool
    allowed_values: dict | None
    source_fields: list[SchemaFieldResponse]

class CanonicalSchema(BaseModel):
    report_schema_id: int
    canonical_fields: list[CanonicalFieldEntry]
