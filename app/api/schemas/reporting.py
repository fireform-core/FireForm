from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.enums import OutputFormat, PeriodType


class GenerateReportRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    period_type: PeriodType
    year: int = Field(ge=2000, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    quarter: int | None = Field(default=None, ge=1, le=4)
    format: OutputFormat = Field(default=OutputFormat.pdf)


class ReportSummaryGroup(BaseModel):
    model_config = ConfigDict()

    period: str
    submission_count: int


class ReportSummary(BaseModel):
    model_config = ConfigDict()

    date_from: date
    date_to: date
    total_submissions: int
    by_template: dict[str, int]
    groups: list[ReportSummaryGroup]


class SubmissionSummaryItem(BaseModel):
    model_config = ConfigDict()

    id: int
    template_id: int
    template_name: str | None = None
    input_text: str | None = None
    output_pdf_path: str
    pdf_url: str | None = None
    created_at: datetime | None = None


class PeriodicReport(BaseModel):
    model_config = ConfigDict()

    report_id: UUID
    period_type: PeriodType
    period_label: str
    generated_at: datetime
    summary: ReportSummary
    submissions: list[SubmissionSummaryItem]


class ReportProgressResponse(BaseModel):
    model_config = ConfigDict()

    message: str = "Report generation is still in progress"
    status: str = "processing"
    retry_after_seconds: int = 10
