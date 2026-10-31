"""Tests for periodic report generation API (Issue #557).

Covers POST /api/v1/reports/generate and GET /api/v1/reports/{report_id},
validation, aggregation logic, compliance metrics, ReportLab PDF generation,
and Celery background worker execution.
"""

from datetime import date
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlmodel import Session, select

from app.api.schemas.enums import (
    FormStatus,
    FormType,
    JobStatus,
    JobType,
    OutputFormat,
    PeriodType,
    ReportStatus,
)
from app.core.config import API_PREFIX
from app.db.repositories import create_job, create_report, get_report
from app.models import Extraction, Form, Incident, Input, Job, Report
from app.services.reporting import ReportingService
from app.tasks.report import generate_periodic_report

GENERATE_URL = f"{API_PREFIX}/reports/generate"
REPORTS_URL = f"{API_PREFIX}/reports"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_incident_with_form(
    db: Session,
    incident_date: date,
    incident_type: str = "fire",
    status: ReportStatus = ReportStatus.draft,
    incident_number: str = "INC-001",
    form_type: FormType = FormType.neris,
    form_status: FormStatus = FormStatus.completed,
    processing_time: float = 12.5,
) -> tuple[Incident, Form]:
    inp = Input(
        input_type="text",
        transcript="Test narrative",
        status="ready",
    )
    db.add(inp)
    db.commit()
    db.refresh(inp)

    ext = Extraction(
        input_id=inp.input_id,
        status="completed",
        processing_time_seconds=processing_time,
        incident_contract={"incident": {"type": incident_type}},
    )
    db.add(ext)
    db.commit()
    db.refresh(ext)

    inc = Incident(
        extract_id=ext.extract_id,
        incident_number=incident_number,
        incident_type=incident_type,
        incident_date=incident_date,
        status=status,
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)

    frm = Form(
        extract_id=ext.extract_id,
        incident_id=inc.incident_id,
        form_type=form_type,
        status=form_status,
    )
    db.add(frm)
    db.commit()
    db.refresh(frm)

    return inc, frm


# ---------------------------------------------------------------------------
# POST /api/v1/reports/generate
# ---------------------------------------------------------------------------

class TestGenerateReportEndpoint:

    @patch("app.api.routes.reports.generate_periodic_report")
    def test_generate_monthly_report_accepted(self, mock_task, client, db):
        resp = client.post(
            GENERATE_URL,
            json={
                "period_type": "monthly",
                "year": 2024,
                "month": 7,
                "format": "pdf",
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        assert "report_id" in data
        assert data["job_type"] == "report_generation"
        assert data["status"] == "processing"
        assert data["estimated_seconds"] == 30
        assert data["poll_url"] == f"{REPORTS_URL}/{data['report_id']}"

        # Verify Report record created in DB
        report = db.exec(select(Report)).first()
        assert report is not None
        assert str(report.report_id) == data["report_id"]
        assert report.period_type == PeriodType.monthly
        assert report.year == 2024
        assert report.month == 7
        assert report.output_format == OutputFormat.pdf
        assert report.status == JobStatus.queued

        # Verify Celery task dispatched with task_id matching job
        job = db.exec(select(Job)).first()
        assert job is not None
        assert job.job_id == data["job_id"]
        mock_task.apply_async.assert_called_once_with(
            (data["report_id"],),
            task_id=job.celery_task_id,
        )

    @patch("app.api.routes.reports.generate_periodic_report")
    def test_generate_quarterly_report_accepted(self, mock_task, client, db):
        resp = client.post(
            GENERATE_URL,
            json={
                "period_type": "quarterly",
                "year": 2024,
                "quarter": 2,
                "format": "json",
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        report = db.exec(select(Report)).first()
        assert data["report_id"] == str(report.report_id)
        assert report.period_type == PeriodType.quarterly
        assert report.quarter == 2
        assert report.output_format == OutputFormat.json

    @patch("app.api.routes.reports.generate_periodic_report")
    def test_generate_annual_report_accepted(self, mock_task, client, db):
        resp = client.post(
            GENERATE_URL,
            json={
                "period_type": "annual",
                "year": 2024,
                "format": "both",
            },
        )
        assert resp.status_code == 202
        report = db.exec(select(Report)).first()
        assert report.period_type == PeriodType.annual
        assert report.output_format == OutputFormat.both

    def test_validation_error_monthly_missing_month(self, client):
        resp = client.post(
            GENERATE_URL,
            json={
                "period_type": "monthly",
                "year": 2024,
            },
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error_code"] == "VALIDATION_ERROR"

    def test_validation_error_quarterly_missing_quarter(self, client):
        resp = client.post(
            GENERATE_URL,
            json={
                "period_type": "quarterly",
                "year": 2024,
            },
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error_code"] == "VALIDATION_ERROR"

    def test_validation_error_invalid_month(self, client):
        resp = client.post(
            GENERATE_URL,
            json={
                "period_type": "monthly",
                "year": 2024,
                "month": 13,
            },
        )
        assert resp.status_code == 422

    def test_validation_error_invalid_quarter(self, client):
        resp = client.post(
            GENERATE_URL,
            json={
                "period_type": "quarterly",
                "year": 2024,
                "quarter": 5,
            },
        )
        assert resp.status_code == 422

    def test_future_period_rejected(self, client):
        resp = client.post(
            GENERATE_URL,
            json={
                "period_type": "annual",
                "year": 2099,
            },
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error_code"] == "FUTURE_PERIOD"

    @patch("app.api.routes.reports.generate_periodic_report")
    def test_celery_queue_unavailable_returns_503(self, mock_task, client, db):
        mock_task.apply_async.side_effect = ConnectionError("Redis broker is down")
        resp = client.post(
            GENERATE_URL,
            json={
                "period_type": "monthly",
                "year": 2024,
                "month": 5,
            },
        )
        assert resp.status_code == 503
        body = resp.json()
        assert body["error_code"] == "QUEUE_UNAVAILABLE"

        job = db.exec(select(Job)).first()
        assert job.status == JobStatus.failed
        assert job.error["error_code"] == "QUEUE_UNAVAILABLE"

        report = db.exec(select(Report)).first()
        assert report.status == JobStatus.failed


# ---------------------------------------------------------------------------
# GET /api/v1/reports/{report_id}
# ---------------------------------------------------------------------------

class TestGetReportEndpoint:

    def test_report_not_found(self, client):
        resp = client.get(f"{REPORTS_URL}/{uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "REPORT_NOT_FOUND"

    def test_report_still_processing_returns_202(self, client, db):
        report = Report(
            period_type=PeriodType.monthly,
            year=2024,
            month=7,
            output_format=OutputFormat.json,
            status=JobStatus.processing,
        )
        db.add(report)
        db.commit()

        resp = client.get(f"{REPORTS_URL}/{report.report_id}")
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "processing"
        assert body["retry_after_seconds"] == 10
        assert "still in progress" in body["message"]

    def test_report_failed_returns_500(self, client, db):
        report = Report(
            period_type=PeriodType.monthly,
            year=2024,
            month=7,
            output_format=OutputFormat.json,
            status=JobStatus.failed,
        )
        db.add(report)
        db.commit()

        resp = client.get(f"{REPORTS_URL}/{report.report_id}")
        assert resp.status_code == 500
        assert resp.json()["error_code"] == "REPORT_FAILED"

    def test_report_completed_json(self, client, db):
        _seed_incident_with_form(db, incident_date=date(2024, 7, 10), incident_type="fire")
        report = Report(
            period_type=PeriodType.monthly,
            year=2024,
            month=7,
            output_format=OutputFormat.json,
            status=JobStatus.queued,
        )
        db.add(report)
        db.commit()

        # Run report generation
        svc = ReportingService()
        svc.generate_report(db, report.report_id)

        # Retrieve completed report
        resp = client.get(f"{REPORTS_URL}/{report.report_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["report_id"] == str(report.report_id)
        assert body["period_type"] == "monthly"
        assert body["period_label"] == "July 2024"
        assert body["summary"]["total_incidents"] == 1
        assert body["summary"]["by_type"] == {"fire": 1}
        assert body["summary"]["forms_generated"] == 1
        assert len(body["incidents"]) == 1
        assert body["incidents"][0]["incident_type"] == "fire"
        assert body["compliance"]["neris_submission_rate"] == 100.0

    def test_report_completed_pdf(self, client, db, tmp_path):
        _seed_incident_with_form(db, incident_date=date(2024, 7, 15), incident_type="ems")
        report = Report(
            period_type=PeriodType.monthly,
            year=2024,
            month=7,
            output_format=OutputFormat.pdf,
            status=JobStatus.queued,
        )
        db.add(report)
        db.commit()

        # Run report generation
        svc = ReportingService()
        svc.generate_report(db, report.report_id)

        # Retrieve PDF
        resp = client.get(f"{REPORTS_URL}/{report.report_id}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert 'attachment; filename="FireForm_Monthly_2024-07.pdf"' in resp.headers.get("content-disposition", "")
        assert resp.content.startswith(b"%PDF")

    def test_report_pdf_file_missing_returns_500(self, client, db):
        report = Report(
            period_type=PeriodType.monthly,
            year=2024,
            month=7,
            output_format=OutputFormat.pdf,
            status=JobStatus.completed,
            pdf_path="/non/existent/path/report.pdf",
        )
        db.add(report)
        db.commit()

        resp = client.get(f"{REPORTS_URL}/{report.report_id}")
        assert resp.status_code == 500
        assert resp.json()["error_code"] == "PDF_NOT_FOUND"


# ---------------------------------------------------------------------------
# ReportingService Aggregation Logic
# ---------------------------------------------------------------------------

class TestReportingServiceAggregation:

    def test_quarterly_aggregation_multiple_incidents(self, db):
        # Q2 2024: April, May, June
        _seed_incident_with_form(db, incident_date=date(2024, 4, 5), incident_type="fire", status=ReportStatus.submitted)
        _seed_incident_with_form(db, incident_date=date(2024, 5, 20), incident_type="ems", status=ReportStatus.approved)
        _seed_incident_with_form(db, incident_date=date(2024, 6, 12), incident_type="ems", status=ReportStatus.draft)
        # Incident outside Q2 (in July)
        _seed_incident_with_form(db, incident_date=date(2024, 7, 1), incident_type="rescue")

        report = Report(
            period_type=PeriodType.quarterly,
            year=2024,
            quarter=2,
            output_format=OutputFormat.json,
            status=JobStatus.queued,
        )
        db.add(report)
        db.commit()

        svc = ReportingService()
        result = svc.generate_report(db, report.report_id)

        assert result.summary.total_incidents == 3
        assert result.summary.by_type == {"fire": 1, "ems": 2}
        assert result.summary.by_status[ReportStatus.submitted.value] == 1
        assert result.summary.by_status[ReportStatus.approved.value] == 1
        assert result.summary.by_status[ReportStatus.draft.value] == 1
        assert len(result.summary.groups) == 3
        assert result.summary.groups[0].period == "2024-04"
        assert result.summary.groups[0].incident_count == 1
        assert result.summary.groups[1].period == "2024-05"
        assert result.summary.groups[1].incident_count == 1
        assert result.summary.groups[2].period == "2024-06"
        assert result.summary.groups[2].incident_count == 1

    def test_empty_period_generates_zero_counts(self, db):
        report = Report(
            period_type=PeriodType.monthly,
            year=2024,
            month=1,
            output_format=OutputFormat.json,
            status=JobStatus.queued,
        )
        db.add(report)
        db.commit()

        svc = ReportingService()
        result = svc.generate_report(db, report.report_id)

        assert result.summary.total_incidents == 0
        assert result.summary.by_type == {}
        assert result.summary.by_status == {}
        assert result.summary.forms_generated == 0
        assert result.compliance.neris_submission_rate == 0.0
        assert result.incidents == []


# ---------------------------------------------------------------------------
# Celery Task: generate_periodic_report
# ---------------------------------------------------------------------------

class TestReportCeleryTask:

    def test_task_completes_job_and_report(self, test_engine):
        with Session(test_engine) as session:
            job = Job(
                job_type=JobType.report_generation,
                celery_task_id="celery-report-task-1",
                status=JobStatus.queued,
            )
            create_job(session, job)

            report = Report(
                period_type=PeriodType.monthly,
                year=2024,
                month=7,
                output_format=OutputFormat.json,
                status=JobStatus.queued,
                job_id=UUID(job.job_id),
            )
            create_report(session, report)
            rep_id = str(report.report_id)

        def _test_session_gen():
            with Session(test_engine) as s:
                yield s

        with patch("app.tasks.report.get_session", _test_session_gen):
            res = generate_periodic_report.apply(
                args=(rep_id,), task_id="celery-report-task-1"
            )

        assert res.result["report_id"] == rep_id

        with Session(test_engine) as session:
            updated_job = session.exec(select(Job).where(Job.celery_task_id == "celery-report-task-1")).first()
            assert updated_job.status == JobStatus.completed
            assert updated_job.progress_percent == 100
            assert updated_job.result_url == f"/api/v1/reports/{rep_id}"

            updated_report = get_report(session, UUID(rep_id))
            assert updated_report.status == JobStatus.completed
            assert updated_report.json_data is not None
            assert updated_report.summary is not None
