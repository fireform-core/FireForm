from sqlmodel import SQLModel, Field, UniqueConstraint
from sqlalchemy import Column, JSON
from datetime import datetime
from enum import Enum

class Template(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    fields: dict = Field(sa_column=Column(JSON))
    pdf_path: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FormSubmission(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    template_id: int
    report_schema_id: int | None = Field(default=None)
    name: str | None = Field(default=None)
    input_text: str
    output_pdf_path: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReportSchema(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    description: str
    use_case: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ReportSchemaTemplate(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    template_id: int
    report_schema_id: int
    field_mapping: dict = Field(default={}, sa_column=Column(JSON))

    __table_args__ = (UniqueConstraint("template_id", "report_schema_id"),)

class Datatype(str, Enum):
    STRING = "string"
    INT = "int"
    DATE = "date"
    ENUM = 'enum'


class SchemaField(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    report_schema_id: int
    field_name: str
    source_template_id: int
    description: str = Field(default="")
    data_type: Datatype = Field(default=Datatype.STRING)
    word_limit: int | None = Field(default=None)
    required: bool = Field(default=False)
    allowed_values: dict | None = Field(sa_column=Column(JSON))
    canonical_name: str | None = Field(default=None)
