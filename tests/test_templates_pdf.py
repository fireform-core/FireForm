"""Tests for the template PDF authoring flow.

Covers POST /templates/pdf, GET /templates/pdf/{upload_id} and
GET /templates/{template_id}/pdf. commonforms never runs here: detection is
dispatched to Celery, and these check the parts around it.
"""

import io
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.api.schemas.enums import DetectionStatus
from app.core.config import API_PREFIX
from app.models import FormTemplate, TemplateUpload

TEMPLATES_URL = f"{API_PREFIX}/templates"


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    """Send stored PDFs to a temp directory instead of the real data dir."""
    target = tmp_path / "templates" / "uploads"
    monkeypatch.setattr("app.services.form_templates.TEMPLATE_UPLOAD_DIR", target)
    monkeypatch.setattr("app.services.form_templates.DATA_DIR", tmp_path)
    return target


@pytest.fixture
def no_celery():
    """Stand in for the detection task so nothing is dispatched to a broker."""
    with patch("app.services.form_templates.detect_template_fields_task") as task:
        task.delay.return_value = MagicMock(id="celery-task-1")
        yield task


def _files(pdf_bytes, name="texas_sfm.pdf"):
    return {"pdf_file": (name, io.BytesIO(pdf_bytes), "application/pdf")}


def _upload(client, pdf_bytes, detect=True, name="texas_sfm.pdf"):
    return client.post(
        f"{TEMPLATES_URL}/pdf",
        files=_files(pdf_bytes, name),
        data={"detect_fields": str(detect).lower()},
    )


# ---------------------------------------------------------------------------
# POST /templates/pdf
# ---------------------------------------------------------------------------
def test_upload_returns_202_with_geometry_and_poll_url(client, pdf_bytes, upload_dir, no_celery):
    resp = _upload(client, pdf_bytes)
    assert resp.status_code == 202, resp.json()
    body = resp.json()

    assert body["status"] == "processing"
    assert body["page_count"] == 1
    assert body["pages"] == [{"page": 0, "width": 612.0, "height": 792.0}]
    assert body["original_filename"] == "texas_sfm.pdf"
    assert body["pdf_template_ref"].endswith(".pdf")
    assert body["poll_url"] == f"/api/v1/templates/pdf/{body['upload_id']}"
    assert body["job_id"]
    assert body["retry_after_seconds"] == 5
    # Detection has not run, so there is no field list yet.
    assert body["detected_fields"] is None


def test_upload_stores_the_pdf_on_disk(client, pdf_bytes, upload_dir, no_celery):
    body = _upload(client, pdf_bytes).json()
    stored = upload_dir / f"{body['upload_id']}.pdf"
    assert stored.read_bytes() == pdf_bytes


def test_upload_dispatches_detection(client, pdf_bytes, upload_dir, no_celery):
    body = _upload(client, pdf_bytes).json()
    no_celery.delay.assert_called_once_with(body["upload_id"], body["job_id"])


def test_upload_without_detection_completes_immediately(client, pdf_bytes, upload_dir, no_celery):
    body = _upload(client, pdf_bytes, detect=False).json()
    assert body["status"] == "completed"
    assert body["detected_fields"] == []
    assert body["job_id"] is None
    assert body["retry_after_seconds"] is None
    no_celery.delay.assert_not_called()


def test_upload_rejects_a_non_pdf(client, upload_dir, no_celery):
    resp = client.post(f"{TEMPLATES_URL}/pdf", files=_files(b"just some text", "notes.pdf"))
    assert resp.status_code == 415
    assert resp.json()["error_code"] == "UNSUPPORTED_FORMAT"


def test_upload_rejects_an_empty_file(client, upload_dir, no_celery):
    resp = client.post(f"{TEMPLATES_URL}/pdf", files=_files(b"", "empty.pdf"))
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "MISSING_FILE"


def test_upload_rejects_an_oversized_pdf(client, upload_dir, no_celery, monkeypatch):
    monkeypatch.setattr("app.api.routes.form_templates.MAX_TEMPLATE_PDF_BYTES", 10)
    resp = client.post(f"{TEMPLATES_URL}/pdf", files=_files(b"%PDF-1.4 padded out here"))
    assert resp.status_code == 413
    assert resp.json()["error_code"] == "FILE_TOO_LARGE"


def test_upload_without_a_file_is_a_422(client, upload_dir, no_celery):
    assert client.post(f"{TEMPLATES_URL}/pdf").status_code == 422


def test_a_pdf_that_cannot_be_read_is_a_415(client, upload_dir, no_celery):
    # Right magic bytes, nothing behind them.
    resp = client.post(f"{TEMPLATES_URL}/pdf", files=_files(b"%PDF-1.4 truncated"))
    assert resp.status_code == 415
    assert resp.json()["error_code"] == "INVALID_PDF"
    assert list(upload_dir.glob("*.pdf")) == []


# ---------------------------------------------------------------------------
# GET /templates/pdf/{upload_id}
# ---------------------------------------------------------------------------
def test_draft_poll_returns_the_stored_state(client, pdf_bytes, upload_dir, no_celery):
    upload_id = _upload(client, pdf_bytes).json()["upload_id"]
    resp = client.get(f"{TEMPLATES_URL}/pdf/{upload_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["upload_id"] == upload_id
    assert body["status"] == "processing"
    assert body["retry_after_seconds"] == 5


def test_draft_poll_after_detection(client, pdf_bytes, upload_dir, no_celery, test_engine):
    upload_id = _upload(client, pdf_bytes).json()["upload_id"]

    with Session(test_engine) as session:
        upload = session.get(TemplateUpload, __import__("uuid").UUID(upload_id))
        upload.status = DetectionStatus.completed
        upload.detected_fields = [
            {
                "field": {
                    "field_name": "incident_number",
                    "field_type": "string",
                    "source": "schema",
                    "required": False,
                    "incident_mapping": "report_metadata.incident_number",
                    "layout": {"page": 0, "x": 10, "y": 20, "width": 100, "height": 18},
                },
                "detected_label": "Incident No.",
                "suggestions": [
                    {"path": "report_metadata.incident_number", "score": 0.93},
                ],
            }
        ]
        session.add(upload)
        session.commit()

    body = client.get(f"{TEMPLATES_URL}/pdf/{upload_id}").json()
    assert body["status"] == "completed"
    assert body["retry_after_seconds"] is None
    field = body["detected_fields"][0]
    assert field["detected_label"] == "Incident No."
    assert field["field"]["incident_mapping"] == "report_metadata.incident_number"
    assert field["suggestions"][0]["score"] == 0.93


def test_draft_poll_reports_a_failed_detection(client, pdf_bytes, upload_dir, no_celery, test_engine):
    from uuid import UUID

    upload_id = _upload(client, pdf_bytes).json()["upload_id"]
    with Session(test_engine) as session:
        upload = session.get(TemplateUpload, UUID(upload_id))
        upload.status = DetectionStatus.failed
        upload.detection_error = "model download failed"
        session.add(upload)
        session.commit()

    body = client.get(f"{TEMPLATES_URL}/pdf/{upload_id}").json()
    assert body["status"] == "failed"
    assert body["detection_error"] == "model download failed"
    # The upload is still usable, geometry and all.
    assert body["page_count"] == 1


def test_draft_poll_unknown_upload_is_404(client):
    resp = client.get(f"{TEMPLATES_URL}/pdf/{uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "UPLOAD_NOT_FOUND"


def test_pdf_path_does_not_shadow_a_template_id(client, pdf_bytes, upload_dir, no_celery):
    """The literal /pdf route has to win over /{template_id}."""
    assert _upload(client, pdf_bytes).status_code == 202


# ---------------------------------------------------------------------------
# GET /templates/{template_id}/pdf
# ---------------------------------------------------------------------------
def _seed_template(session, pdf_template_ref):
    template = FormTemplate(
        form_type="state_texas",
        display_name="Texas SFM",
        fields=[],
        pdf_template_ref=pdf_template_ref,
    )
    session.add(template)
    session.commit()
    session.refresh(template)
    return template.template_id


def test_download_source_pdf(client, pdf_bytes, upload_dir, no_celery, test_engine, tmp_path):
    upload = _upload(client, pdf_bytes).json()
    with Session(test_engine) as session:
        template_id = _seed_template(session, upload["pdf_template_ref"])

    resp = client.get(f"{TEMPLATES_URL}/{template_id}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == pdf_bytes


def test_download_without_a_source_pdf_is_404(client, upload_dir, test_engine):
    with Session(test_engine) as session:
        template_id = _seed_template(session, None)
    resp = client.get(f"{TEMPLATES_URL}/{template_id}/pdf")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "TEMPLATE_PDF_NOT_FOUND"


def test_download_missing_file_is_404(client, upload_dir, test_engine):
    with Session(test_engine) as session:
        template_id = _seed_template(session, "templates/uploads/gone.pdf")
    assert client.get(f"{TEMPLATES_URL}/{template_id}/pdf").status_code == 404


def test_download_cannot_escape_the_data_directory(client, upload_dir, test_engine, tmp_path):
    outside = tmp_path.parent / "secret.pdf"
    outside.write_bytes(b"%PDF-1.4 secret")
    with Session(test_engine) as session:
        template_id = _seed_template(session, "../secret.pdf")

    resp = client.get(f"{TEMPLATES_URL}/{template_id}/pdf")
    assert resp.status_code == 404


def test_download_unknown_template_is_404(client):
    assert client.get(f"{TEMPLATES_URL}/{uuid4()}/pdf").status_code == 404
