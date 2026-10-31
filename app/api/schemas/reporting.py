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
    incident_count: int
    forms_generated: int


class ReportSummary(BaseModel):
    model_config = ConfigDict()

    date_from: date
    date_to: date
    total_incidents: int
    by_type: dict[str, int]
    by_status: dict[str, int]
    forms_generated: int
    avg_completeness_score: float
    avg_processing_time_seconds: float
    groups: list[ReportSummaryGroup]


class IncidentSummaryItem(BaseModel):
    model_config = ConfigDict()

    incident_id: UUID
    incident_number: str | None = None
    incident_date: date | None = None
    incident_type: str | None = None
    status: str | None = None
    forms_generated: int = 0


class ReportCompliance(BaseModel):
    model_config = ConfigDict()

    neris_submission_rate: float
    average_submission_delay_days: float
    overdue_incidents: int


class PeriodicReport(BaseModel):
    model_config = ConfigDict()

    report_id: UUID
    period_type: PeriodType
    period_label: str
    generated_at: datetime
    summary: ReportSummary
    incidents: list[IncidentSummaryItem]
    compliance: ReportCompliance


class ReportProgressResponse(BaseModel):
    model_config = ConfigDict()

    message: str = "Report generation is still in progress"
    status: str = "processing"
    retry_after_seconds: int = 10
