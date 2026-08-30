"""Tests for the batch form-fill worker (app/services/form_fill_worker.py).

Runs the real ReportLab-draw / pypdf-merge pipeline against the minimal valid
PDF from conftest — no mocking of the drawing itself, only the filesystem
location (redirected to tmp_path). Covers: field resolution onto pdf/json
output, the field_mapping_summary shape, status transitions, and per-form
failure isolation (one bad form doesn't sink the batch or the job).
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pypdf import PdfReader

from app.api.schemas.enums import (
    ExtractionStatus,
    FormStatus,
    InputStatus,
    InputType,
    JobStatus,
    ReportStatus,
)
from app.db.repositories import (
    create_extraction,
    create_form_template,
    create_generated_form,
    create_incident,
    create_input,
    create_job,
    get_job_by_uuid,
)
from app.models import Extraction, Form, FormTemplate, Incident, Input, Job
from app.services.form_fill_worker import fill_one, run_batch_fill

_CONTRACT = {
    "schema_version": "1.1.0",
    "schema_name": "fireform_incident_contract",
    "incident": {"name": "Bear Creek Wildfire"},
    "location": {"city": "Reno", "state": "NV"},
    "custom_fields": {"neris.marshal_signature_name": "A. Ruiz"},
}


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _layout(page=0, x=50, y=700, width=200, height=20, **extra) -> dict:
    return {"page": page, "x": x, "y": y, "width": width, "height": height, **extra}


def _field(name, source="schema", required=True, layout=None, **extra) -> dict:
    field = {
        "field_name": name,
        "field_type": "string",
        "source": source,
        "required": required,
        "layout": layout,
    }
    if source == "schema":
        field.setdefault("incident_mapping", "incident.name")
    if source == "static":
        field.setdefault("static_text", "Reno Fire Department")
    if source == "manual":
        pass
    field.update(extra)
    return field


def _incident(db, contract=None) -> Incident:
    now = datetime.now(timezone.utc)
    inp = create_input(
        db,
        Input(
            input_type=InputType.text,
            status=InputStatus.ready,
            transcript="Wildfire off Bear Creek, no injuries.",
            created_at=now,
            updated_at=now,
        ),
    )
    extraction = create_extraction(
        db,
        Extraction(input_id=inp.input_id, status=ExtractionStatus.completed, started_at=now, completed_at=now),
    )
    return create_incident(
        db,
        Incident(
            extract_id=extraction.extract_id,
            status=ReportStatus.draft,
            incident_contract=_CONTRACT if contract is None else contract,
        ),
    )


def _template(db, form_type="neris", fields=None, pdf_template_ref=None) -> FormTemplate:
    return create_form_template(
        db,
        FormTemplate(
            form_type=form_type,
            display_name=form_type.upper(),
            fields=fields if fields is not None else [_field("incident_name", layout=_layout())],
            pdf_template_ref=pdf_template_ref,
        ),
    )


def _form(db, incident, template, batch_id=None, **kwargs) -> Form:
    defaults = dict(
        template_id=template.template_id,
        incident_id=incident.incident_id,
        batch_id=batch_id,
        form_type=template.form_type,
        status=FormStatus.queued,
    )
    return create_generated_form(db, Form(**{**defaults, **kwargs}))


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    """Redirect the template-source lookup and the fill output to tmp_path,
    same pattern test_templates_pdf.py uses for the upload flow."""
    monkeypatch.setattr("app.services.form_templates.DATA_DIR", tmp_path)
    monkeypatch.setattr("app.services.form_fill_worker.DATA_DIR", tmp_path)
    generated = tmp_path / "forms" / "generated"
    monkeypatch.setattr("app.services.form_fill_worker.FORMS_OUTPUT_DIR", generated)
    return tmp_path


def _seed_template_pdf(tmp_path, pdf_bytes, name="template.pdf") -> str:
    """Write the source PDF under tmp_path and return its DATA_DIR-relative ref."""
    path = tmp_path / "templates" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf_bytes)
    return str(path.relative_to(tmp_path))


# ---------------------------------------------------------------------------
# fill_one
# ---------------------------------------------------------------------------

class TestFillOne:

    def test_fills_schema_static_and_manual_fields(self, db, output_dir, pdf_bytes):
        ref = _seed_template_pdf(output_dir, pdf_bytes)
        incident = _incident(db)
        template = _template(
            db,
            fields=[
                _field("incident_name", source="schema", incident_mapping="incident.name", layout=_layout(y=700)),
                _field("agency", source="static", layout=_layout(y=650)),
                _field("marshal_signature_name", source="manual", required=False, layout=None),
            ],
            pdf_template_ref=ref,
        )
        form = _form(db, incident, template)

        fill_one(db, form)

        assert form.status == FormStatus.completed
        assert form.pdf_ready is True
        assert form.json_ready is True
        assert form.completed_at is not None

        # pdf_path is DATA_DIR-relative and the file is a real, readable PDF.
        assert not form.pdf_path.startswith("/")
        written = output_dir / form.pdf_path
        assert written.is_file()
        reader = PdfReader(str(written))
        assert len(reader.pages) == 1

        # agency_fields covers every field, placed or not.
        assert form.json_data["incident_name"] == "Bear Creek Wildfire"
        assert form.json_data["agency"] == "Reno Fire Department"
        assert form.json_data["marshal_signature_name"] == "A. Ruiz"

        summary = form.field_mapping_summary
        assert summary["total_form_fields"] == 3
        assert summary["fields_filled"] == 3
        assert summary["fields_blank"] == 0
        assert summary["coverage_percent"] == 100.0

    def test_unplaced_field_has_no_layout_but_is_still_in_json(self, db, output_dir, pdf_bytes):
        ref = _seed_template_pdf(output_dir, pdf_bytes)
        incident = _incident(db)
        template = _template(
            db,
            fields=[_field("incident_name", layout=None)],
            pdf_template_ref=ref,
        )
        form = _form(db, incident, template)

        fill_one(db, form)

        assert form.status == FormStatus.completed
        assert form.json_data["incident_name"] == "Bear Creek Wildfire"

    def test_missing_required_field_still_fills_a_blank_box(self, db, output_dir, pdf_bytes):
        """Filling doesn't gate on readiness — that's the generate-time skip check."""
        ref = _seed_template_pdf(output_dir, pdf_bytes)
        incident = _incident(db, contract={"schema_version": "1.1.0", "schema_name": "fireform_incident_contract"})
        template = _template(
            db,
            fields=[_field("incident_name", source="schema", incident_mapping="incident.name", layout=_layout())],
            pdf_template_ref=ref,
        )
        form = _form(db, incident, template)

        fill_one(db, form)

        assert form.status == FormStatus.completed
        assert form.json_data["incident_name"] is None
        assert form.field_mapping_summary["fields_blank"] == 1
        assert form.field_mapping_summary["coverage_percent"] == 0.0

    def test_missing_template_pdf_raises(self, db, output_dir):
        incident = _incident(db)
        template = _template(
            db,
            fields=[_field("incident_name", layout=_layout())],
            pdf_template_ref="templates/does-not-exist.pdf",
        )
        form = _form(db, incident, template)

        with pytest.raises(Exception):
            fill_one(db, form)


# ---------------------------------------------------------------------------
# run_batch_fill — batch orchestration and per-form failure isolation
# ---------------------------------------------------------------------------

class TestRunBatchFill:

    def _job(self, db) -> Job:
        return create_job(db, Job(celery_task_id="task-1", job_type="batch_form_generation", status="queued"))

    def test_all_forms_complete_job_completed(self, db, output_dir, pdf_bytes):
        ref = _seed_template_pdf(output_dir, pdf_bytes)
        incident = _incident(db)
        template = _template(db, fields=[_field("incident_name", layout=_layout())], pdf_template_ref=ref)
        batch_id = uuid4()
        _form(db, incident, template, batch_id=batch_id)
        _form(db, incident, template, batch_id=batch_id)
        job = self._job(db)

        result = run_batch_fill(db, batch_id, job.job_id)

        assert result["completed"] == 2
        assert result["failed"] == 0
        refreshed = get_job_by_uuid(db, job.job_id)
        assert refreshed.status == JobStatus.completed
        assert refreshed.progress_percent == 100

    def test_one_bad_form_does_not_sink_the_batch(self, db, output_dir, pdf_bytes):
        """One form's template PDF is missing; the other form in the same
        batch still completes, and the Job still finishes as completed."""
        good_ref = _seed_template_pdf(output_dir, pdf_bytes, name="good.pdf")
        good_template = _template(db, fields=[_field("incident_name", layout=_layout())], pdf_template_ref=good_ref)
        bad_template = _template(
            db,
            form_type="cal_fire_ics209",
            fields=[_field("incident_name", layout=_layout())],
            pdf_template_ref="templates/missing.pdf",
        )
        incident = _incident(db)
        batch_id = uuid4()
        good_form = _form(db, incident, good_template, batch_id=batch_id)
        bad_form = _form(db, incident, bad_template, batch_id=batch_id)
        job = self._job(db)

        result = run_batch_fill(db, batch_id, job.job_id)

        assert result["completed"] == 1
        assert result["failed"] == 1

        from app.db.repositories import get_form
        assert get_form(db, good_form.form_id).status == FormStatus.completed
        assert get_form(db, bad_form.form_id).status == FormStatus.failed

        refreshed_job = get_job_by_uuid(db, job.job_id)
        assert refreshed_job.status == JobStatus.completed
        assert refreshed_job.progress_percent == 100

    def test_empty_batch_completes_cleanly(self, db, output_dir):
        job = self._job(db)
        result = run_batch_fill(db, uuid4(), job.job_id)
        assert result == {"batch_id": result["batch_id"], "completed": 0, "failed": 0}
        assert get_job_by_uuid(db, job.job_id).status == JobStatus.completed
