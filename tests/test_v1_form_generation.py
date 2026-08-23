"""Tests for POST /forms/generate, GET /forms/batch/{batch_id}, GET /forms/{form_id},
GET /forms/{form_id}/pdf and GET /forms/{form_id}/json.

Dispatch is mocked (no broker) — the actual fill is covered by
tests/test_v1_form_fill_worker.py. These cover the write path (queued vs
skipped split, 404s, the NO_FORMS_TO_GENERATE case) and the read endpoints
against Form rows seeded directly.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from app.api.schemas.enums import (
    ExtractionStatus,
    FormStatus,
    InputStatus,
    InputType,
    ReportStatus,
)
from app.core.config import API_PREFIX
from app.db.repositories import (
    create_extraction,
    create_form_template,
    create_generated_form,
    create_incident,
    create_input,
)
from app.models import Extraction, Form, FormTemplate, Incident, Input

FORMS_URL = f"{API_PREFIX}/forms"

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
    if source == "open":
        field.setdefault("description", "Anything the narrative says about it")
    field.update(extra)
    return field


def _incident(db, contract=None, incident_number=None) -> Incident:
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
        Extraction(
            input_id=inp.input_id,
            status=ExtractionStatus.completed,
            started_at=now,
            completed_at=now,
        ),
    )
    return create_incident(
        db,
        Incident(
            extract_id=extraction.extract_id,
            status=ReportStatus.draft,
            incident_contract=_CONTRACT if contract is None else contract,
            incident_number=incident_number,
        ),
    )


def _template(db, form_type="neris", fields=None) -> FormTemplate:
    return create_form_template(
        db,
        FormTemplate(
            form_type=form_type,
            display_name=form_type.upper(),
            fields=fields if fields is not None else [_field("incident_name")],
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


class NoCelery:
    """Stand-in for the fill task so nothing is dispatched to a broker."""

    def __enter__(self):
        self._patch = patch("app.services.form_generation.generate_forms_batch_task")
        self.task = self._patch.__enter__()
        self.task.delay.return_value = MagicMock(id="celery-batch-1")
        return self.task

    def __exit__(self, *exc):
        self._patch.__exit__(*exc)


# ---------------------------------------------------------------------------
# POST /forms/generate
# ---------------------------------------------------------------------------

class TestGenerateForms:

    def test_202_all_ready_queues_every_template(self, client, db):
        incident = _incident(db)
        template = _template(db, fields=[_field("incident_name")])

        with NoCelery() as task:
            resp = client.post(
                f"{FORMS_URL}/generate",
                json={"incident_id": str(incident.incident_id), "template_ids": [str(template.template_id)]},
            )

        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "processing"
        assert body["incident_id"] == str(incident.incident_id)
        assert len(body["forms_queued"]) == 1
        assert body["forms_queued"][0]["template_id"] == str(template.template_id)
        assert body["forms_queued"][0]["form_type"] == "neris"
        assert body["forms_skipped"] == []
        assert body["poll_url"] == f"/api/v1/forms/batch/{body['batch_id']}"
        assert body["estimated_seconds"] == 10
        task.delay.assert_called_once()
        dispatched_batch_id, dispatched_job_id = task.delay.call_args[0]
        assert dispatched_batch_id == body["batch_id"]
        assert isinstance(dispatched_job_id, str) and dispatched_job_id

    def test_not_ready_template_is_skipped_with_reason(self, client, db):
        # A not-ready template alone would 422 NO_FORMS_TO_GENERATE (covered
        # separately below) — pair it with a ready one so the skip path is
        # exercised inside a batch that still succeeds.
        incident = _incident(db)
        ready = _template(db, form_type="neris", fields=[_field("incident_name")])
        not_ready = _template(
            db,
            form_type="state_texas",
            fields=[_field("marshal_signature_name", source="manual", required=True)],
        )

        with NoCelery():
            resp = client.post(
                f"{FORMS_URL}/generate",
                json={
                    "incident_id": str(incident.incident_id),
                    "template_ids": [str(ready.template_id), str(not_ready.template_id)],
                },
            )

        assert resp.status_code == 202
        body = resp.json()
        assert len(body["forms_queued"]) == 1
        assert len(body["forms_skipped"]) == 1
        skipped = body["forms_skipped"][0]
        assert skipped["template_id"] == str(not_ready.template_id)
        assert skipped["reason"] == "Not ready: marshal_signature_name (manual) has no value"

    def test_force_partial_queues_a_not_ready_template(self, client, db):
        incident = _incident(db, contract={"schema_version": "1.1.0", "schema_name": "fireform_incident_contract"})
        template = _template(
            db,
            form_type="state_texas",
            fields=[_field("marshal_signature_name", source="manual", required=True)],
        )

        with NoCelery():
            resp = client.post(
                f"{FORMS_URL}/generate",
                json={
                    "incident_id": str(incident.incident_id),
                    "template_ids": [str(template.template_id)],
                    "options": {"force_partial": True},
                },
            )

        assert resp.status_code == 202
        body = resp.json()
        assert body["forms_skipped"] == []
        assert len(body["forms_queued"]) == 1

    def test_mixed_batch_splits_queued_and_skipped(self, client, db):
        incident = _incident(db)
        ready = _template(db, form_type="neris", fields=[_field("incident_name")])
        not_ready = _template(
            db,
            form_type="cal_fire_ics209",
            fields=[_field("something_missing", source="schema", incident_mapping="does.not.exist")],
        )

        with NoCelery():
            resp = client.post(
                f"{FORMS_URL}/generate",
                json={
                    "incident_id": str(incident.incident_id),
                    "template_ids": [str(ready.template_id), str(not_ready.template_id)],
                },
            )

        body = resp.json()
        assert len(body["forms_queued"]) == 1
        assert len(body["forms_skipped"]) == 1
        assert body["forms_queued"][0]["template_id"] == str(ready.template_id)
        assert body["forms_skipped"][0]["template_id"] == str(not_ready.template_id)

    def test_creates_queued_form_rows_in_db(self, client, db, test_engine):
        from sqlmodel import Session, select

        incident = _incident(db)
        template = _template(db)

        with NoCelery():
            resp = client.post(
                f"{FORMS_URL}/generate",
                json={"incident_id": str(incident.incident_id), "template_ids": [str(template.template_id)]},
            )
        batch_id = UUID(resp.json()["batch_id"])

        with Session(test_engine) as session:
            rows = list(session.exec(select(Form).where(Form.batch_id == batch_id)))
        assert len(rows) == 1
        assert rows[0].status == FormStatus.queued
        assert rows[0].incident_id == incident.incident_id
        assert rows[0].template_id == template.template_id

    def test_404_incident_not_found(self, client, db):
        template = _template(db)
        with NoCelery():
            resp = client.post(
                f"{FORMS_URL}/generate",
                json={"incident_id": str(uuid4()), "template_ids": [str(template.template_id)]},
            )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "INCIDENT_NOT_FOUND"

    def test_404_template_not_found(self, client, db):
        incident = _incident(db)
        with NoCelery():
            resp = client.post(
                f"{FORMS_URL}/generate",
                json={"incident_id": str(incident.incident_id), "template_ids": [str(uuid4())]},
            )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "TEMPLATE_NOT_FOUND"

    def test_404_on_bad_template_leaves_no_partial_batch(self, client, db, test_engine):
        """A bad template_id anywhere in the list 404s before any Form row is written."""
        from sqlmodel import Session, select

        incident = _incident(db)
        good = _template(db)
        with NoCelery():
            resp = client.post(
                f"{FORMS_URL}/generate",
                json={
                    "incident_id": str(incident.incident_id),
                    "template_ids": [str(good.template_id), str(uuid4())],
                },
            )
        assert resp.status_code == 404
        with Session(test_engine) as session:
            rows = list(session.exec(select(Form)))
        assert rows == []

    def test_422_empty_template_ids_rejected(self, client, db):
        incident = _incident(db)
        resp = client.post(
            f"{FORMS_URL}/generate",
            json={"incident_id": str(incident.incident_id), "template_ids": []},
        )
        assert resp.status_code == 422

    def test_422_no_forms_to_generate_when_all_skipped(self, client, db):
        incident = _incident(db, contract={"schema_version": "1.1.0", "schema_name": "fireform_incident_contract"})
        template = _template(
            db,
            form_type="state_texas",
            fields=[_field("marshal_signature_name", source="manual", required=True)],
        )
        with NoCelery():
            resp = client.post(
                f"{FORMS_URL}/generate",
                json={"incident_id": str(incident.incident_id), "template_ids": [str(template.template_id)]},
            )
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "NO_FORMS_TO_GENERATE"


# ---------------------------------------------------------------------------
# GET /forms/batch/{batch_id}
# ---------------------------------------------------------------------------

class TestBatchStatus:

    def test_processing_when_some_forms_still_queued(self, client, db):
        incident = _incident(db)
        template = _template(db)
        batch_id = uuid4()
        _form(db, incident, template, batch_id=batch_id, status=FormStatus.queued)
        _form(db, incident, template, batch_id=batch_id, status=FormStatus.completed)

        resp = client.get(f"{FORMS_URL}/batch/{batch_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "processing"
        assert body["total"] == 2
        assert body["completed"] == 1
        assert body["failed"] == 0
        assert body["download_url"] is None

    def test_completed_when_all_terminal_with_no_failures(self, client, db):
        incident = _incident(db)
        template = _template(db)
        batch_id = uuid4()
        _form(db, incident, template, batch_id=batch_id, status=FormStatus.completed)
        _form(db, incident, template, batch_id=batch_id, status=FormStatus.completed)

        resp = client.get(f"{FORMS_URL}/batch/{batch_id}")
        assert resp.json()["status"] == "completed"

    def test_completed_when_terminal_with_a_partial_failure(self, client, db):
        """One failed form doesn't fail the batch — matches the per-form isolation design."""
        incident = _incident(db)
        template = _template(db)
        batch_id = uuid4()
        _form(db, incident, template, batch_id=batch_id, status=FormStatus.completed)
        _form(db, incident, template, batch_id=batch_id, status=FormStatus.failed)

        resp = client.get(f"{FORMS_URL}/batch/{batch_id}")
        body = resp.json()
        assert body["status"] == "completed"
        assert body["completed"] == 1
        assert body["failed"] == 1

    def test_failed_when_every_form_failed(self, client, db):
        incident = _incident(db)
        template = _template(db)
        batch_id = uuid4()
        _form(db, incident, template, batch_id=batch_id, status=FormStatus.failed)

        resp = client.get(f"{FORMS_URL}/batch/{batch_id}")
        assert resp.json()["status"] == "failed"

    def test_404_unknown_batch(self, client, db):
        resp = client.get(f"{FORMS_URL}/batch/{uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "BATCH_NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /forms/{form_id}
# ---------------------------------------------------------------------------

class TestGetForm:

    def test_200_returns_form_record(self, client, db):
        incident = _incident(db)
        template = _template(db)
        summary = {
            "total_form_fields": 10,
            "fields_filled": 8,
            "fields_blank": 2,
            "coverage_percent": 80.0,
        }
        form = _form(
            db, incident, template,
            status=FormStatus.completed,
            pdf_ready=True,
            json_ready=True,
            field_mapping_summary=summary,
        )

        resp = client.get(f"{FORMS_URL}/{form.form_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["form_id"] == str(form.form_id)
        assert body["template_id"] == str(template.template_id)
        assert body["form_type"] == "neris"
        assert body["status"] == "completed"
        assert body["incident_id"] == str(incident.incident_id)
        assert body["pdf_ready"] is True
        assert body["json_ready"] is True
        assert body["field_mapping_summary"]["coverage_percent"] == 80.0

    def test_404_unknown_form(self, client, db):
        resp = client.get(f"{FORMS_URL}/{uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "FORM_NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /forms/{form_id}/pdf
# ---------------------------------------------------------------------------

class TestGetFormPdf:

    def test_202_while_still_generating(self, client, db):
        incident = _incident(db)
        template = _template(db)
        form = _form(db, incident, template, status=FormStatus.generating)

        resp = client.get(f"{FORMS_URL}/{form.form_id}/pdf")
        assert resp.status_code == 202
        assert resp.json()["status"] == "generating"

    def test_500_when_form_failed(self, client, db):
        incident = _incident(db)
        template = _template(db)
        form = _form(db, incident, template, status=FormStatus.failed)

        resp = client.get(f"{FORMS_URL}/{form.form_id}/pdf")
        assert resp.status_code == 500
        assert resp.json()["error_code"] == "PDF_GENERATION_FAILED"

    def _completed_pdf_form(self, db, tmp_path, pdf_bytes, incident, template):
        pdf_file = tmp_path / "forms" / "generated" / "x.pdf"
        pdf_file.parent.mkdir(parents=True, exist_ok=True)
        pdf_file.write_bytes(pdf_bytes)
        return _form(
            db, incident, template,
            status=FormStatus.completed,
            pdf_ready=True,
            pdf_path="forms/generated/x.pdf",
        )

    def test_200_serves_the_pdf_file(self, client, db, monkeypatch, tmp_path, pdf_bytes):
        monkeypatch.setattr("app.api.routes.form_generation.DATA_DIR", tmp_path)
        incident = _incident(db, incident_number="FF-2024-CA-0157")
        template = _template(db)
        form = self._completed_pdf_form(db, tmp_path, pdf_bytes, incident, template)

        resp = client.get(f"{FORMS_URL}/{form.form_id}/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content == pdf_bytes
        assert 'filename="neris_FF-2024-CA-0157.pdf"' in resp.headers["content-disposition"]

    def test_filename_falls_back_to_form_id_without_an_incident_number(
        self, client, db, monkeypatch, tmp_path, pdf_bytes
    ):
        monkeypatch.setattr("app.api.routes.form_generation.DATA_DIR", tmp_path)
        incident = _incident(db)
        template = _template(db)
        form = self._completed_pdf_form(db, tmp_path, pdf_bytes, incident, template)

        resp = client.get(f"{FORMS_URL}/{form.form_id}/pdf")
        assert f'filename="{form.form_id}.pdf"' in resp.headers["content-disposition"]

    def test_filename_strips_characters_an_incident_number_should_not_carry(
        self, client, db, monkeypatch, tmp_path, pdf_bytes
    ):
        monkeypatch.setattr("app.api.routes.form_generation.DATA_DIR", tmp_path)
        incident = _incident(db, incident_number='../2024 "07"/0157')
        template = _template(db)
        form = self._completed_pdf_form(db, tmp_path, pdf_bytes, incident, template)

        resp = client.get(f"{FORMS_URL}/{form.form_id}/pdf")
        assert 'filename="neris_2024-07-0157.pdf"' in resp.headers["content-disposition"]

    def test_404_path_escaping_data_dir_is_rejected(self, client, db, monkeypatch, tmp_path):
        monkeypatch.setattr("app.api.routes.form_generation.DATA_DIR", tmp_path)
        incident = _incident(db)
        template = _template(db)
        form = _form(
            db, incident, template,
            status=FormStatus.completed,
            pdf_ready=True,
            pdf_path="../../etc/passwd",
        )

        resp = client.get(f"{FORMS_URL}/{form.form_id}/pdf")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /forms/{form_id}/json
# ---------------------------------------------------------------------------

class TestGetFormJson:

    def test_200_returns_agency_fields(self, client, db):
        incident = _incident(db)
        template = _template(db)
        form = _form(
            db, incident, template,
            status=FormStatus.completed,
            json_ready=True,
            json_data={"incident_name": "Bear Creek Wildfire"},
        )

        resp = client.get(f"{FORMS_URL}/{form.form_id}/json")
        assert resp.status_code == 200
        body = resp.json()
        assert body["form_id"] == str(form.form_id)
        assert body["agency_fields"]["incident_name"] == "Bear Creek Wildfire"
        assert body["form_version"] == template.version

    def test_202_while_still_generating(self, client, db):
        incident = _incident(db)
        template = _template(db)
        form = _form(db, incident, template, status=FormStatus.queued)

        resp = client.get(f"{FORMS_URL}/{form.form_id}/json")
        assert resp.status_code == 202
        assert resp.json()["status"] == "queued"
        assert resp.json()["retry_after_seconds"] == 5

    def test_500_when_form_failed(self, client, db):
        incident = _incident(db)
        template = _template(db)
        form = _form(db, incident, template, status=FormStatus.failed)

        resp = client.get(f"{FORMS_URL}/{form.form_id}/json")
        assert resp.status_code == 500
        assert resp.json()["error_code"] == "FORM_GENERATION_FAILED"

    def test_404_unknown_form(self, client, db):
        resp = client.get(f"{FORMS_URL}/{uuid4()}/json")
        assert resp.status_code == 404
