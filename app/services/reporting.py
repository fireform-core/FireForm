from __future__ import annotations

import calendar
import html
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlmodel import Session

from app.api.schemas.enums import (
    JobStatus,
    OutputFormat,
    PeriodType,
)
from app.api.schemas.reporting import (
    GenerateReportRequest,
    PeriodicReport,
    ReportSummary,
    ReportSummaryGroup,
    SubmissionSummaryItem,
)
from app.core.config import REPORTS_DIR
from app.core.errors.base import AppError
from app.db.repositories import (
    get_report,
    get_submissions_in_date_range,
    update_report,
)

logger = logging.getLogger(__name__)


class ReportingService:
    """Business logic for periodic report generation and analytics."""

    def validate_and_compute_bounds(
        self, req: GenerateReportRequest
    ) -> tuple[date, date, str, str]:
        """Validate report parameters and compute date range, label, and PDF filename.

        Returns (date_from, date_to, period_label, pdf_filename).
        Raises AppError with 422 if validation fails or a future period is requested.
        """
        now = datetime.now(timezone.utc)

        if req.period_type == PeriodType.monthly:
            if req.month is None:
                raise AppError(
                    "month is required when period_type is monthly",
                    status_code=422,
                    error_code="VALIDATION_ERROR",
                    detail={"validation_errors": [{"field": "month", "issue": "Missing required field"}]},
                )
            if req.month < 1 or req.month > 12:
                raise AppError(
                    "month must be between 1 and 12",
                    status_code=422,
                    error_code="VALIDATION_ERROR",
                    detail={"validation_errors": [{"field": "month", "issue": "Must be 1..12", "value": req.month}]},
                )
            if req.year > now.year or (req.year == now.year and req.month > now.month):
                raise AppError(
                    "Cannot generate a report for a future period",
                    status_code=422,
                    error_code="FUTURE_PERIOD",
                )
            date_from = date(req.year, req.month, 1)
            _, last_day = calendar.monthrange(req.year, req.month)
            date_to = date(req.year, req.month, last_day)
            period_label = f"{calendar.month_name[req.month]} {req.year}"
            pdf_filename = f"FireForm_Monthly_{req.year}-{req.month:02d}.pdf"

        elif req.period_type == PeriodType.quarterly:
            if req.quarter is None:
                raise AppError(
                    "quarter is required when period_type is quarterly",
                    status_code=422,
                    error_code="VALIDATION_ERROR",
                    detail={"validation_errors": [{"field": "quarter", "issue": "Missing required field"}]},
                )
            if req.quarter < 1 or req.quarter > 4:
                raise AppError(
                    "Invalid quarter value",
                    status_code=422,
                    error_code="VALIDATION_ERROR",
                    detail={"validation_errors": [{"field": "quarter", "issue": "Must be 1, 2, 3, or 4", "value": req.quarter}]},
                )
            current_quarter = (now.month - 1) // 3 + 1
            if req.year > now.year or (req.year == now.year and req.quarter > current_quarter):
                raise AppError(
                    "Cannot generate a report for a future period",
                    status_code=422,
                    error_code="FUTURE_PERIOD",
                )
            start_month = (req.quarter - 1) * 3 + 1
            end_month = start_month + 2
            date_from = date(req.year, start_month, 1)
            _, last_day = calendar.monthrange(req.year, end_month)
            date_to = date(req.year, end_month, last_day)
            period_label = f"Q{req.quarter} {req.year}"
            pdf_filename = f"FireForm_Quarterly_{req.year}-Q{req.quarter}.pdf"

        elif req.period_type == PeriodType.annual:
            if req.year > now.year:
                raise AppError(
                    "Cannot generate a report for a future period",
                    status_code=422,
                    error_code="FUTURE_PERIOD",
                )
            date_from = date(req.year, 1, 1)
            date_to = date(req.year, 12, 31)
            period_label = f"{req.year}"
            pdf_filename = f"FireForm_Annual_{req.year}.pdf"

        else:
            raise AppError(
                f"Unsupported period type: {req.period_type}",
                status_code=422,
                error_code="VALIDATION_ERROR",
            )

        return date_from, date_to, period_label, pdf_filename

    def generate_report(self, session: Session, report_id: UUID) -> PeriodicReport:
        """Core report generation pipeline: queries form submissions, aggregates metrics, and builds PDF/JSON."""
        report = get_report(session, report_id)
        if not report:
            raise AppError(f"Report {report_id} not found", status_code=404, error_code="REPORT_NOT_FOUND")

        # Re-derive period bounds
        req = GenerateReportRequest(
            period_type=report.period_type,
            year=report.year,
            month=report.month,
            quarter=report.quarter,
            format=report.output_format,
        )
        date_from, date_to, period_label, pdf_filename = self.validate_and_compute_bounds(req)

        # 1. Fetch form submissions in date range (joined with template name)
        submissions_raw = get_submissions_in_date_range(session, date_from, date_to)

        # 2. Compute statistics & breakdowns
        total_submissions = len(submissions_raw)
        by_template: dict[str, int] = {}
        for _, template_name in submissions_raw:
            tname = template_name or "Unknown Template"
            by_template[tname] = by_template.get(tname, 0) + 1

        # Sort by_template descending by count
        by_template = dict(sorted(by_template.items(), key=lambda item: item[1], reverse=True))

        # Period groups breakdown
        groups: list[ReportSummaryGroup] = []
        if report.period_type == PeriodType.monthly:
            groups.append(
                ReportSummaryGroup(
                    period=f"{report.year}-{report.month:02d}",
                    submission_count=total_submissions,
                )
            )
        elif report.period_type == PeriodType.quarterly:
            start_m = (report.quarter - 1) * 3 + 1
            for m in range(start_m, start_m + 3):
                m_label = f"{report.year}-{m:02d}"
                m_count = sum(
                    1
                    for sub, _ in submissions_raw
                    if sub.created_at and sub.created_at.month == m
                )
                groups.append(
                    ReportSummaryGroup(
                        period=m_label,
                        submission_count=m_count,
                    )
                )
        elif report.period_type == PeriodType.annual:
            for m in range(1, 13):
                m_label = f"{report.year}-{m:02d}"
                m_count = sum(
                    1
                    for sub, _ in submissions_raw
                    if sub.created_at and sub.created_at.month == m
                )
                groups.append(
                    ReportSummaryGroup(
                        period=m_label,
                        submission_count=m_count,
                    )
                )

        summary = ReportSummary(
            date_from=date_from,
            date_to=date_to,
            total_submissions=total_submissions,
            by_template=by_template,
            groups=groups,
        )

        submission_items = [
            SubmissionSummaryItem(
                id=sub.id,
                template_id=sub.template_id,
                template_name=template_name,
                input_text=sub.input_text,
                output_pdf_path=sub.output_pdf_path,
                pdf_url=f"/api/v1/templates/preview?path={quote(sub.output_pdf_path)}" if sub.output_pdf_path else None,
                created_at=sub.created_at,
            )
            for sub, template_name in submissions_raw
        ]

        now_utc = datetime.now(timezone.utc)
        periodic_report = PeriodicReport(
            report_id=report.report_id,
            period_type=report.period_type,
            period_label=period_label,
            generated_at=now_utc,
            summary=summary,
            submissions=submission_items,
        )

        # 3. Generate PDF if format requires it
        pdf_path_str: str | None = None
        if report.output_format in (OutputFormat.pdf, OutputFormat.both):
            pdf_path = Path(REPORTS_DIR) / pdf_filename
            self._generate_pdf(pdf_path, periodic_report)
            pdf_path_str = str(pdf_path)

        # 4. Update database record
        report.status = JobStatus.completed
        report.period_label = period_label
        report.generated_at = now_utc
        report.summary = summary.model_dump(mode="json")
        report.json_data = periodic_report.model_dump(mode="json")
        report.pdf_path = pdf_path_str
        report.updated_at = now_utc
        update_report(session, report)

        return periodic_report

    def _generate_pdf(self, output_path: Path, report: PeriodicReport) -> None:
        """Render a clean ReportLab PDF document for the periodic report."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40,
        )
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Heading1"],
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#b91c1c"),  # FireForm red
            spaceAfter=6,
        )
        subtitle_style = ParagraphStyle(
            "ReportSubtitle",
            parent=styles["Normal"],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#4b5563"),
            spaceAfter=14,
        )
        section_style = ParagraphStyle(
            "SectionHeading",
            parent=styles["Heading2"],
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#1f2937"),
            spaceBefore=12,
            spaceAfter=6,
        )
        cell_style = ParagraphStyle(
            "CellNormal",
            parent=styles["Normal"],
            fontSize=9,
            leading=11,
        )
        header_cell_style = ParagraphStyle(
            "HeaderCell",
            parent=styles["Normal"],
            fontSize=9,
            leading=11,
            textColor=colors.white,
            fontName="Helvetica-Bold",
        )

        elements = []

        # Header
        elements.append(Paragraph("FireForm Periodic Report", title_style))
        gen_str = report.generated_at.strftime("%Y-%m-%d %H:%M UTC")
        elements.append(
            Paragraph(f"Period: <b>{html.escape(report.period_label)}</b> | Generated on {gen_str}", subtitle_style)
        )
        elements.append(Spacer(1, 10))

        # Executive Summary Table
        elements.append(Paragraph("Executive Summary", section_style))
        most_active_template = (
            next(iter(report.summary.by_template.keys()), "None")
            if report.summary.by_template
            else "None"
        )
        summary_data = [
            [
                Paragraph("<b>Metric</b>", header_cell_style),
                Paragraph("<b>Value</b>", header_cell_style),
                Paragraph("<b>Metric</b>", header_cell_style),
                Paragraph("<b>Value</b>", header_cell_style),
            ],
            [
                Paragraph("Total Submissions", cell_style),
                Paragraph(str(report.summary.total_submissions), cell_style),
                Paragraph("Date Range", cell_style),
                Paragraph(f"{report.summary.date_from} to {report.summary.date_to}", cell_style),
            ],
            [
                Paragraph("Templates Used", cell_style),
                Paragraph(str(len(report.summary.by_template)), cell_style),
                Paragraph("Most Active Template", cell_style),
                Paragraph(html.escape(most_active_template), cell_style),
            ],
        ]
        summary_table = Table(summary_data, colWidths=[133, 133, 133, 133])
        summary_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b91c1c")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elements.append(summary_table)
        elements.append(Spacer(1, 12))

        # Template Breakdown Table
        elements.append(Paragraph("Breakdown by Template", section_style))
        breakdown_data = [
            [
                Paragraph("<b>Template Name</b>", header_cell_style),
                Paragraph("<b>Submissions Count</b>", header_cell_style),
                Paragraph("<b>Share</b>", header_cell_style),
            ]
        ]
        if not report.summary.by_template:
            breakdown_data.append([
                Paragraph("No submissions in period", cell_style),
                Paragraph("0", cell_style),
                Paragraph("0.0%", cell_style),
            ])
        else:
            total = max(1, report.summary.total_submissions)
            for t_name, count in report.summary.by_template.items():
                pct = (count / total) * 100.0
                breakdown_data.append([
                    Paragraph(html.escape(t_name), cell_style),
                    Paragraph(str(count), cell_style),
                    Paragraph(f"{pct:.1f}%", cell_style),
                ])

        breakdown_table = Table(breakdown_data, colWidths=[312, 110, 110])
        breakdown_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#374151")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elements.append(breakdown_table)
        elements.append(Spacer(1, 12))

        # Submission Records Table
        elements.append(Paragraph("Form Submission Records", section_style))
        sub_data = [
            [
                Paragraph("<b>ID</b>", header_cell_style),
                Paragraph("<b>Date & Time</b>", header_cell_style),
                Paragraph("<b>Template</b>", header_cell_style),
                Paragraph("<b>Input Preview</b>", header_cell_style),
                Paragraph("<b>Output PDF</b>", header_cell_style),
            ]
        ]
        if not report.submissions:
            sub_data.append([
                Paragraph("No submissions in period", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
            ])
        else:
            for sub in report.submissions[:50]:  # Cap at 50 rows for the PDF document
                created_str = (
                    sub.created_at.strftime("%Y-%m-%d %H:%M")
                    if sub.created_at
                    else "-"
                )
                input_preview = (
                    (sub.input_text[:60] + "...")
                    if sub.input_text and len(sub.input_text) > 60
                    else (sub.input_text or "-")
                )
                pdf_name = Path(sub.output_pdf_path).name if sub.output_pdf_path else "-"
                sub_data.append([
                    Paragraph(f"#{sub.id}", cell_style),
                    Paragraph(created_str, cell_style),
                    Paragraph(html.escape(sub.template_name or "Unknown"), cell_style),
                    Paragraph(html.escape(input_preview), cell_style),
                    Paragraph(html.escape(pdf_name), cell_style),
                ])

        sub_table = Table(sub_data, colWidths=[50, 95, 120, 167, 100])
        sub_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ])
        )
        elements.append(sub_table)

        doc.build(elements)
