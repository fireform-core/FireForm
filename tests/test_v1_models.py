"""Direct SQLModel instantiation tests for the five v1 models.

Uses the same in-memory SQLite engine and _reset_tables fixture from conftest
(autouse=True) so every test starts with a clean schema. Tests stay at the ORM
layer — no routes, no Celery, no Ollama.
"""

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, select

from app.api.schemas.enums import (
    ExtractionStatus,
    FormStatus,
    FormType,
    IncidentCategory,
    InputStatus,
    InputType,
    JobStatus,
    OutputFormat,
    PeriodType,
    ReportStatus,
)
from app.models import Extraction, Form, FormTemplate, Incident, Input, Report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _input(db: Session, **kwargs) -> Input:
    defaults = dict(input_type=InputType.text)
    row = Input(**{**defaults, **kwargs})
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _extraction(db: Session, input_id: UUID, **kwargs) -> "Extraction":
    row = Extraction(input_id=input_id, **kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _incident(db: Session, **kwargs) -> Incident:
    inp = _input(db)
    ext = _extraction(db, inp.input_id)
    defaults = dict(extract_id=ext.extract_id)
    row = Incident(**{**defaults, **kwargs})
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _form_template(db: Session, **kwargs) -> FormTemplate:
    defaults = dict(form_type=f"test_form_{uuid4().hex[:8]}", display_name="Test Form", fields=[])
    row = FormTemplate(**{**defaults, **kwargs})
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

class TestInputModel:

    def test_defaults_on_create(self, db):
        row = _input(db)
        assert isinstance(row.input_id, UUID)
        assert row.status == InputStatus.queued
        assert row.transcript is None
        assert row.audio_duration_seconds is None
        assert row.character_count is None
        assert isinstance(row.created_at, datetime)
        assert isinstance(row.updated_at, datetime)

    def test_voice_fields_roundtrip(self, db):
        row = _input(
            db,
            input_type=InputType.voice,
            original_filename="call_recording.mp3",
            audio_duration_seconds=47.3,
            station_id="STA-12",
            responder_badge="B-4421",
            incident_date_hint=date(2026, 6, 1),
        )
        fetched = db.get(Input, row.input_id)
        assert fetched.input_type == InputType.voice
        assert fetched.original_filename == "call_recording.mp3"
        assert fetched.audio_duration_seconds == pytest.approx(47.3)
        assert fetched.station_id == "STA-12"
        assert fetched.incident_date_hint == date(2026, 6, 1)

    def test_status_transitions_persist(self, db):
        row = _input(db)
        row.status = InputStatus.transcribing
        db.add(row)
        db.commit()
        fetched = db.get(Input, row.input_id)
        assert fetched.status == InputStatus.transcribing

    def test_error_detail_on_failed(self, db):
        row = _input(db, status=InputStatus.failed, error_detail="Whisper timeout")
        fetched = db.get(Input, row.input_id)
        assert fetched.status == InputStatus.failed
        assert fetched.error_detail == "Whisper timeout"

    def test_word_and_char_counts(self, db):
        row = _input(
            db,
            status=InputStatus.ready,
            transcript="Structure fire at 4th and Main",
            character_count=30,
            word_count=6,
        )
        fetched = db.get(Input, row.input_id)
        assert fetched.character_count == 30
        assert fetched.word_count == 6

    def test_unique_primary_keys(self, db):
        a = _input(db)
        b = _input(db)
        assert a.input_id != b.input_id


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

class TestExtractionModel:

    def test_defaults_on_create(self, db):
        inp = _input(db)
        ext = _extraction(db, inp.input_id)
        assert isinstance(ext.extract_id, UUID)
        assert ext.input_id == inp.input_id
        assert ext.status == ExtractionStatus.processing
        assert ext.partial_result is None
        assert ext.corrections is None
        assert ext.started_at is None

    def test_partial_result_json_roundtrip(self, db):
        inp = _input(db)
        partial = {
            "schema_version": "1.1.0",
            "incident": {"name": "Structure Fire Main St", "types": []},
            "location": {"address": "123 Main St", "state": "CA"},
        }
        ext = _extraction(db, inp.input_id, partial_result=partial)
        fetched = db.get(Extraction, ext.extract_id)
        assert fetched.partial_result["schema_version"] == "1.1.0"
        assert fetched.partial_result["location"]["state"] == "CA"

    def test_corrections_json_roundtrip(self, db):
        inp = _input(db)
        corrections = [
            {
                "field_path": "incident.name",
                "original_value": "Wildland Fire",
                "corrected_value": "Structure Fire",
                "corrected_at": "2026-06-26T10:00:00Z",
                "corrected_by": "dispatcher_01",
            }
        ]
        ext = _extraction(db, inp.input_id, corrections=corrections)
        fetched = db.get(Extraction, ext.extract_id)
        assert len(fetched.corrections) == 1
        assert fetched.corrections[0]["field_path"] == "incident.name"

    def test_completed_status_fields(self, db):
        inp = _input(db)
        now = datetime.now(timezone.utc)
        ext = _extraction(
            db,
            inp.input_id,
            status=ExtractionStatus.completed,
            started_at=now,
            completed_at=now,
            model_used="llama3:8b",
            processing_time_seconds=38.4,
        )
        fetched = db.get(Extraction, ext.extract_id)
        assert fetched.status == ExtractionStatus.completed
        assert fetched.model_used == "llama3:8b"
        assert fetched.processing_time_seconds == pytest.approx(38.4)

    def test_failed_status_with_error_fields(self, db):
        inp = _input(db)
        ext = _extraction(
            db,
            inp.input_id,
            status=ExtractionStatus.failed,
            error_type="LLM_TIMEOUT",
            error_detail="Ollama did not respond within 120s",
        )
        fetched = db.get(Extraction, ext.extract_id)
        assert fetched.status == ExtractionStatus.failed
        assert fetched.error_type == "LLM_TIMEOUT"


# ---------------------------------------------------------------------------
# Incident
# ---------------------------------------------------------------------------

class TestIncidentModel:

    def _make(self, db, **kwargs):
        inp = _input(db)
        ext = _extraction(db, inp.input_id)
        defaults = dict(extract_id=ext.extract_id)
        row = Incident(**{**defaults, **kwargs})
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def test_defaults_on_create(self, db):
        row = self._make(db)
        assert isinstance(row.incident_id, UUID)
        assert row.status == ReportStatus.draft
        assert row.deleted_at is None
        assert row.tags is None

    def test_tags_json_roundtrip(self, db):
        row = self._make(db, tags=["wildland", "high-priority", "multi-agency"])
        fetched = db.get(Incident, row.incident_id)
        assert fetched.tags == ["wildland", "high-priority", "multi-agency"]

    def test_soft_delete(self, db):
        row = self._make(db)
        assert row.deleted_at is None
        ts = datetime.now(timezone.utc)
        row.deleted_at = ts
        db.add(row)
        db.commit()
        fetched = db.get(Incident, row.incident_id)
        assert fetched.deleted_at is not None

    def test_all_nullable_fields_default_none(self, db):
        row = self._make(db)
        assert row.incident_number is None
        assert row.incident_name is None
        assert row.incident_type is None
        assert row.notes is None

    def test_incident_contract_json_roundtrip(self, db):
        contract = {
            "schema_version": "1.1.0",
            "incident": {"name": "Structure Fire Main St", "types": []},
            "location": {"address": "123 Main St", "state": "CA"},
        }
        row = self._make(db, incident_contract=contract)
        fetched = db.get(Incident, row.incident_id)
        assert fetched.incident_contract["schema_version"] == "1.1.0"
        assert fetched.incident_contract["location"]["state"] == "CA"

    def test_promoted_columns_default_none(self, db):
        row = self._make(db)
        assert row.incident_contract is None
        assert row.incident_category is None
        assert row.incident_datetime is None
        assert row.city is None
        assert row.civilian_injuries is None
        assert row.area_burned_ha is None
        assert row.total_loss_amount is None
        assert row.call_to_arrival_seconds is None

    def test_promoted_columns_roundtrip(self, db):
        row = self._make(
            db,
            incident_category=IncidentCategory.fire,
            incident_datetime=datetime(2026, 5, 15, 14, 30, tzinfo=timezone.utc),
            city="Oakland",
            state="CA",
            country="US",
            civilian_injuries=2,
            responder_fatalities=0,
            people_evacuated=40,
            structures_destroyed=3,
            area_burned_ha=12.5,
            total_loss_amount=250000.0,
            total_loss_currency="USD",
            call_to_arrival_seconds=312,
        )
        fetched = db.get(Incident, row.incident_id)
        assert fetched.incident_category == IncidentCategory.fire
        assert fetched.city == "Oakland"
        assert fetched.civilian_injuries == 2
        assert fetched.area_burned_ha == pytest.approx(12.5)
        assert fetched.total_loss_currency == "USD"
        assert fetched.call_to_arrival_seconds == 312


# ---------------------------------------------------------------------------
# Form
# ---------------------------------------------------------------------------

class TestFormModel:

    def _make(self, db, **kwargs):
        template = _form_template(db)
        incident = _incident(db)
        defaults = dict(
            template_id=template.template_id,
            incident_id=incident.incident_id,
            form_type=FormType.nfirs_basic,
        )
        row = Form(**{**defaults, **kwargs})
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def test_defaults_on_create(self, db):
        row = self._make(db)
        assert isinstance(row.form_id, UUID)
        assert row.status == FormStatus.queued
        assert row.pdf_ready is False
        assert row.json_ready is False
        assert isinstance(row.template_id, UUID)
        assert isinstance(row.incident_id, UUID)
        assert row.batch_id is None
        assert row.job_id is None
        assert row.completed_at is None

    def test_field_mapping_summary_roundtrip(self, db):
        summary = {
            "total_form_fields": 42,
            "fields_filled": 38,
            "fields_blank": 4,
            "coverage_percent": 90.5,
        }
        row = self._make(db, field_mapping_summary=summary)
        fetched = db.get(Form, row.form_id)
        assert fetched.field_mapping_summary["total_form_fields"] == 42
        assert fetched.field_mapping_summary["coverage_percent"] == pytest.approx(90.5)

    def test_json_data_roundtrip(self, db):
        agency_json = {"FDID": "CA99901", "INC_NO": "2026-0042", "ALARMS": 2}
        row = self._make(db, json_data=agency_json, json_ready=True)
        fetched = db.get(Form, row.form_id)
        assert fetched.json_ready is True
        assert fetched.json_data["FDID"] == "CA99901"

    def test_incident_fk_links_correctly(self, db):
        template = _form_template(db)
        incident = _incident(db)

        form = Form(
            template_id=template.template_id,
            form_type=FormType.neris,
            incident_id=incident.incident_id,
        )
        db.add(form)
        db.commit()
        db.refresh(form)
        assert form.incident_id == incident.incident_id

    def test_template_fk_links_correctly(self, db):
        template = _form_template(db)
        incident = _incident(db)

        form = Form(
            template_id=template.template_id,
            form_type=FormType.neris,
            incident_id=incident.incident_id,
        )
        db.add(form)
        db.commit()
        db.refresh(form)
        assert form.template_id == template.template_id

    def test_batch_id_roundtrip(self, db):
        """batch_id is a plain UUID grouping key — no Batch table, no FK."""
        batch_id = uuid4()
        row = self._make(db, batch_id=batch_id)
        fetched = db.get(Form, row.form_id)
        assert fetched.batch_id == batch_id

    def test_job_id_stored_without_fk(self, db):
        """job_id is a plain UUID — can store any UUID without a FK constraint."""
        arbitrary_uuid = uuid4()
        row = self._make(db, job_id=arbitrary_uuid)
        fetched = db.get(Form, row.form_id)
        assert fetched.job_id == arbitrary_uuid

    def test_all_form_types_accepted(self, db):
        template = _form_template(db)
        incident = _incident(db)
        for ft in FormType:
            form = Form(
                template_id=template.template_id,
                incident_id=incident.incident_id,
                form_type=ft,
            )
            db.add(form)
        db.commit()
        results = db.exec(select(Form)).all()
        stored_types = {f.form_type for f in results}
        assert stored_types == set(FormType)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

class TestReportModel:

    def _make(self, db, **kwargs):
        defaults = dict(
            period_type=PeriodType.monthly,
            year=2026,
            month=6,
            output_format=OutputFormat.pdf,
        )
        row = Report(**{**defaults, **kwargs})
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def test_defaults_on_create(self, db):
        row = self._make(db)
        assert isinstance(row.report_id, UUID)
        assert row.status == JobStatus.queued
        assert row.generated_at is None
        assert row.summary is None
        assert row.pdf_path is None
        assert row.json_data is None
        assert row.job_id is None

    def test_summary_json_roundtrip(self, db):
        summary = {
            "total_incidents": 23,
            "by_type": {"fire": 10, "ems": 13},
            "forms_generated": 71,
            "avg_completeness_score": 88.3,
        }
        row = self._make(db, summary=summary)
        fetched = db.get(Report, row.report_id)
        assert fetched.summary["total_incidents"] == 23
        assert fetched.summary["avg_completeness_score"] == pytest.approx(88.3)

    def test_quarterly_report(self, db):
        row = self._make(
            db,
            period_type=PeriodType.quarterly,
            year=2026,
            month=None,
            quarter=2,
            output_format=OutputFormat.json,
        )
        fetched = db.get(Report, row.report_id)
        assert fetched.period_type == PeriodType.quarterly
        assert fetched.quarter == 2
        assert fetched.month is None

    def test_annual_report(self, db):
        row = self._make(
            db,
            period_type=PeriodType.annual,
            year=2025,
            month=None,
            quarter=None,
            output_format=OutputFormat.both,
        )
        fetched = db.get(Report, row.report_id)
        assert fetched.period_type == PeriodType.annual
        assert fetched.year == 2025
        assert fetched.output_format == OutputFormat.both

    def test_job_id_stored_without_fk(self, db):
        arbitrary_uuid = uuid4()
        row = self._make(db, job_id=arbitrary_uuid)
        fetched = db.get(Report, row.report_id)
        assert fetched.job_id == arbitrary_uuid

    def test_status_progression(self, db):
        row = self._make(db)
        assert row.status == JobStatus.queued
        row.status = JobStatus.processing
        db.add(row)
        db.commit()
        fetched = db.get(Report, row.report_id)
        assert fetched.status == JobStatus.processing
