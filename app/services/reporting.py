from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlmodel import Session

from app.api.schemas.enums import (
    FormStatus,
    FormType,
    JobStatus,
    OutputFormat,
    PeriodType,
    ReportStatus,
)
from app.api.schemas.reporting import (
    GenerateReportRequest,
    IncidentSummaryItem,
    PeriodicReport,
    ReportCompliance,
    ReportSummary,
    ReportSummaryGroup,
)
from app.core.config import REPORTS_DIR
from app.core.errors.base import AppError
from app.db.repositories import (
    get_extractions_by_ids,
    get_forms_for_incidents,
    get_incidents_in_date_range,
    get_report,
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
        """Core report generation pipeline: queries data, aggregates metrics, and builds PDF/JSON."""
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

        # 1. Fetch incidents in date range
        incidents = get_incidents_in_date_range(session, date_from, date_to)
        incident_ids = [inc.incident_id for inc in incidents]

        # 2. Fetch associated forms and extractions
        forms = get_forms_for_incidents(session, incident_ids)
        incident_forms_map: dict[UUID, list] = {inc_id: [] for inc_id in incident_ids}
        for f in forms:
            if f.incident_id in incident_forms_map:
                incident_forms_map[f.incident_id].append(f)

        extract_ids = [inc.extract_id for inc in incidents if inc.extract_id is not None]
        extractions = get_extractions_by_ids(session, extract_ids)
        extractions_map = {ext.extract_id: ext for ext in extractions}

        # 3. Compute statistics & breakdowns
        total_incidents = len(incidents)
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for inc in incidents:
            itype = inc.incident_type or "unspecified"
            by_type[itype] = by_type.get(itype, 0) + 1
            st = inc.status.value if hasattr(inc.status, "value") else str(inc.status)
            by_status[st] = by_status.get(st, 0) + 1

        completed_forms_count = sum(1 for f in forms if f.status == FormStatus.completed)

        # Processing time
        processing_times = [
            ext.processing_time_seconds
            for ext in extractions
            if ext.processing_time_seconds is not None
        ]
        avg_processing_time = (
            round(sum(processing_times) / len(processing_times), 1) if processing_times else 0.0
        )

        # Completeness score
        completeness_scores = []
        for inc in incidents:
            ext = extractions_map.get(inc.extract_id)
            if ext and ext.incident_contract:
                # Estimate completeness based on populated top-level contract keys
                populated = sum(1 for v in ext.incident_contract.values() if v is not None and v != "")
                total = len(ext.incident_contract)
                score = (populated / total * 100.0) if total > 0 else 100.0
                completeness_scores.append(score)
            elif total_incidents > 0:
                completeness_scores.append(100.0)
        avg_completeness = (
            round(sum(completeness_scores) / len(completeness_scores), 1)
            if completeness_scores
            else (100.0 if total_incidents > 0 else 0.0)
        )

        # Period groups breakdown
        groups: list[ReportSummaryGroup] = []
        if report.period_type == PeriodType.monthly:
            groups.append(
                ReportSummaryGroup(
                    period=f"{report.year}-{report.month:02d}",
                    incident_count=total_incidents,
                    forms_generated=completed_forms_count,
                )
            )
        elif report.period_type == PeriodType.quarterly:
            start_m = (report.quarter - 1) * 3 + 1
            for m in range(start_m, start_m + 3):
                m_label = f"{report.year}-{m:02d}"
                m_inc_count = sum(
                    1
                    for inc in incidents
                    if (inc.incident_date and inc.incident_date.month == m)
                    or (not inc.incident_date and inc.created_at.month == m)
                )
                m_forms_count = sum(
                    len([f for f in incident_forms_map.get(inc.incident_id, []) if f.status == FormStatus.completed])
                    for inc in incidents
                    if (inc.incident_date and inc.incident_date.month == m)
                    or (not inc.incident_date and inc.created_at.month == m)
                )
                groups.append(
                    ReportSummaryGroup(
                        period=m_label,
                        incident_count=m_inc_count,
                        forms_generated=m_forms_count,
                    )
                )
        elif report.period_type == PeriodType.annual:
            for m in range(1, 13):
                m_label = f"{report.year}-{m:02d}"
                m_inc_count = sum(
                    1
                    for inc in incidents
                    if (inc.incident_date and inc.incident_date.month == m)
                    or (not inc.incident_date and inc.created_at.month == m)
                )
                m_forms_count = sum(
                    len([f for f in incident_forms_map.get(inc.incident_id, []) if f.status == FormStatus.completed])
                    for inc in incidents
                    if (inc.incident_date and inc.incident_date.month == m)
                    or (not inc.incident_date and inc.created_at.month == m)
                )
                groups.append(
                    ReportSummaryGroup(
                        period=m_label,
                        incident_count=m_inc_count,
                        forms_generated=m_forms_count,
                    )
                )

        # 4. Compliance metrics
        # NERIS submission rate: incidents with completed NERIS form or submitted status
        neris_submitted = 0
        delays = []
        overdue_count = 0
        today = datetime.now(timezone.utc).date()

        for inc in incidents:
            has_neris = any(
                f.form_type == FormType.neris and f.status == FormStatus.completed
                for f in incident_forms_map.get(inc.incident_id, [])
            )
            is_submitted = inc.status == ReportStatus.submitted or has_neris
            if is_submitted:
                neris_submitted += 1
                inc_date = inc.incident_date or inc.created_at.date()
                delay = (inc.updated_at.date() - inc_date).days
                delays.append(max(0, delay))
            elif inc.status in (ReportStatus.draft, ReportStatus.under_review):
                inc_date = inc.incident_date or inc.created_at.date()
                if (today - inc_date).days > 30:
                    overdue_count += 1

        neris_rate = round((neris_submitted / total_incidents * 100.0), 1) if total_incidents > 0 else 0.0
        avg_delay = round(sum(delays) / len(delays), 1) if delays else 0.0

        compliance = ReportCompliance(
            neris_submission_rate=neris_rate,
            average_submission_delay_days=avg_delay,
            overdue_incidents=overdue_count,
        )

        summary = ReportSummary(
            date_from=date_from,
            date_to=date_to,
            total_incidents=total_incidents,
            by_type=by_type,
            by_status=by_status,
            forms_generated=completed_forms_count,
            avg_completeness_score=avg_completeness,
            avg_processing_time_seconds=avg_processing_time,
            groups=groups,
        )

        incident_items = [
            IncidentSummaryItem(
                incident_id=inc.incident_id,
                incident_number=inc.incident_number,
                incident_date=inc.incident_date or inc.created_at.date(),
                incident_type=inc.incident_type,
                status=inc.status.value if hasattr(inc.status, "value") else str(inc.status),
                forms_generated=len([f for f in incident_forms_map.get(inc.incident_id, []) if f.status == FormStatus.completed]),
            )
            for inc in incidents
        ]

        now_utc = datetime.now(timezone.utc)
        periodic_report = PeriodicReport(
            report_id=report.report_id,
            period_type=report.period_type,
            period_label=period_label,
            generated_at=now_utc,
            summary=summary,
            incidents=incident_items,
            compliance=compliance,
        )

        # 5. Generate PDF if format requires it
        pdf_path_str: str | None = None
        if report.output_format in (OutputFormat.pdf, OutputFormat.both):
            pdf_path = Path(REPORTS_DIR) / pdf_filename
            self._generate_pdf(pdf_path, periodic_report)
            pdf_path_str = str(pdf_path)

        # 6. Update database record
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
            Paragraph(f"Period: <b>{report.period_label}</b> | Generated on {gen_str}", subtitle_style)
        )
        elements.append(Spacer(1, 10))

        # Executive Summary Table
        elements.append(Paragraph("Executive Summary", section_style))
        summary_data = [
            [
                Paragraph("<b>Metric</b>", header_cell_style),
                Paragraph("<b>Value</b>", header_cell_style),
                Paragraph("<b>Metric</b>", header_cell_style),
                Paragraph("<b>Value</b>", header_cell_style),
            ],
            [
                Paragraph("Total Incidents", cell_style),
                Paragraph(str(report.summary.total_incidents), cell_style),
                Paragraph("Forms Generated", cell_style),
                Paragraph(str(report.summary.forms_generated), cell_style),
            ],
            [
                Paragraph("Avg Completeness", cell_style),
                Paragraph(f"{report.summary.avg_completeness_score}%", cell_style),
                Paragraph("Avg Processing Time", cell_style),
                Paragraph(f"{report.summary.avg_processing_time_seconds}s", cell_style),
            ],
        ]
        summary_table = Table(summary_data, colWidths=[130, 130, 130, 130])
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

        # Compliance Table
        elements.append(Paragraph("Compliance Metrics (USFA / NERIS)", section_style))
        compliance_data = [
            [
                Paragraph("<b>Metric</b>", header_cell_style),
                Paragraph("<b>Value</b>", header_cell_style),
            ],
            [
                Paragraph("NERIS Submission Rate", cell_style),
                Paragraph(f"{report.compliance.neris_submission_rate}%", cell_style),
            ],
            [
                Paragraph("Average Submission Delay", cell_style),
                Paragraph(f"{report.compliance.average_submission_delay_days} days", cell_style),
            ],
            [
                Paragraph("Overdue Incidents (>30 days unsubmitted)", cell_style),
                Paragraph(str(report.compliance.overdue_incidents), cell_style),
            ],
        ]
        comp_table = Table(compliance_data, colWidths=[260, 260])
        comp_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#374151")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elements.append(comp_table)
        elements.append(Spacer(1, 12))

        # Breakdowns: By Type and By Status
        elements.append(Paragraph("Breakdown by Category & Status", section_style))
        type_rows = [f"{k}: {v}" for k, v in report.summary.by_type.items()] or ["None"]
        status_rows = [f"{k}: {v}" for k, v in report.summary.by_status.items()] or ["None"]
        max_rows = max(len(type_rows), len(status_rows))

        breakdown_data = [
            [
                Paragraph("<b>Incident Category</b>", header_cell_style),
                Paragraph("<b>Report Status</b>", header_cell_style),
            ]
        ]
        for i in range(max_rows):
            t_val = type_rows[i] if i < len(type_rows) else ""
            s_val = status_rows[i] if i < len(status_rows) else ""
            breakdown_data.append([
                Paragraph(t_val, cell_style),
                Paragraph(s_val, cell_style),
            ])

        breakdown_table = Table(breakdown_data, colWidths=[260, 260])
        breakdown_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4b5563")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elements.append(breakdown_table)
        elements.append(Spacer(1, 12))

        # Incident List
        elements.append(Paragraph("Incident Records", section_style))
        inc_data = [
            [
                Paragraph("<b>Incident #</b>", header_cell_style),
                Paragraph("<b>Date</b>", header_cell_style),
                Paragraph("<b>Type</b>", header_cell_style),
                Paragraph("<b>Status</b>", header_cell_style),
                Paragraph("<b>Forms</b>", header_cell_style),
            ]
        ]
        if not report.incidents:
            inc_data.append([
                Paragraph("No incidents in period", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
            ])
        else:
            for inc in report.incidents[:50]:  # Limit to 50 rows per report document
                inc_data.append([
                    Paragraph(inc.incident_number or str(inc.incident_id)[:8], cell_style),
                    Paragraph(inc.incident_date.isoformat() if inc.incident_date else "-", cell_style),
                    Paragraph(inc.incident_type or "-", cell_style),
                    Paragraph(inc.status or "-", cell_style),
                    Paragraph(str(inc.forms_generated), cell_style),
                ])

        inc_table = Table(inc_data, colWidths=[120, 80, 120, 120, 80])
        inc_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ])
        )
        elements.append(inc_table)

        doc.build(elements)
