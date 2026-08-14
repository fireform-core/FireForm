"""Comprehensive API tests for FireForm.

Covers every endpoint and the full upload → template → fill pipeline.
All heavy dependencies (LLM, commonforms, filesystem) are mocked via conftest.
"""

from uuid import uuid4

from sqlmodel import select

from app.api.schemas.enums import InputStatus, InputType
from app.models import Template, FormSubmission, Input
from app.core.config import API_PREFIX
from app.models import FormSubmission, Template

# ═══════════════════════════════════════════════════════════════════════════
# DB model sanity
# ═══════════════════════════════════════════════════════════════════════════

class TestDBModels:
    """Verify the ORM models roundtrip correctly."""

    def test_template_roundtrip(self, db):
        tpl = Template(
            name="Incident Report",
            fields={"name": "string", "date": "string"},
            pdf_path="src/inputs/incident.pdf",
        )
        db.add(tpl)
        db.commit()
        db.refresh(tpl)

        fetched = db.get(Template, tpl.id)
        assert fetched is not None
        assert fetched.name == "Incident Report"
        assert fetched.fields == {"name": "string", "date": "string"}
        assert fetched.pdf_path == "src/inputs/incident.pdf"
        assert fetched.created_at is not None

    def test_form_submission_roundtrip(self, db):
        # Need a template first (FK reference)
        tpl = Template(name="T", fields={}, pdf_path="t.pdf")
        db.add(tpl)
        db.commit()
        db.refresh(tpl)

        input_record = Input(
            input_type=InputType.text, status=InputStatus.ready, transcript="John Doe, firefighter"
        )
        db.add(input_record)
        db.commit()
        db.refresh(input_record)

        sub = FormSubmission(
            template_id=tpl.id,
            input_id=input_record.input_id,
            input_text="John Doe, firefighter",
            output_pdf_path="src/outputs/filled.pdf",
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)

        fetched = db.get(FormSubmission, sub.id)
        assert fetched is not None
        assert fetched.template_id == tpl.id
        assert fetched.input_id == input_record.input_id
        assert fetched.input_text == "John Doe, firefighter"
        assert fetched.created_at is not None

    def test_list_templates_ordering(self, db):
        """Templates should come back newest-first."""
        import time

        t1 = Template(name="First", fields={}, pdf_path="a.pdf")
        db.add(t1)
        db.commit()

        time.sleep(0.05)  # ensure different timestamps

        t2 = Template(name="Second", fields={}, pdf_path="b.pdf")
        db.add(t2)
        db.commit()

        results = list(
            db.exec(select(Template).order_by(Template.created_at.desc()))
        )
        assert results[0].name == "Second"
        assert results[1].name == "First"


# ═══════════════════════════════════════════════════════════════════════════
# Template endpoints
# ═══════════════════════════════════════════════════════════════════════════

class TestTemplateEndpoints:

    def test_list_templates_empty(self, client):
        resp = client.get(f"{API_PREFIX}/templates")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_template(self, client, mock_controller):
        payload = {
            "name": "Fire Report",
            "pdf_path": "src/inputs/fire_report.pdf",
            "fields": {
                "Name": "string",
                "Date": "string",
                "Location": "string",
            },
        }
        resp = client.post(f"{API_PREFIX}/templates/create", json=payload)
        assert resp.status_code == 200

        data = resp.json()
        assert data["id"] is not None
        assert data["name"] == "Fire Report"
        assert data["fields"]["Location"] == "string"
        # Plain create just persists the row; commonforms only runs via
        # the separate /make-fillable endpoint.
        mock_controller["template_ctrl"].create_template.assert_not_called()

    def test_create_then_list(self, client, mock_controller):
        """Creating a template should make it appear in the list."""
        client.post(f"{API_PREFIX}/templates/create", json={
            "name": "T1",
            "pdf_path": "a.pdf",
            "fields": {"f": "string"},
        })
        resp = client.get(f"{API_PREFIX}/templates")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["name"] == "T1"

    def test_upload_pdf(self, client, pdf_upload, tmp_path, monkeypatch):
        """Upload a valid PDF file."""
        # Point the upload directory inside tmp_path (which is inside the project
        # for the path-safety check — we monkeypatch the check).
        monkeypatch.setattr(
            "app.services.template.PROJECT_ROOT",
            tmp_path,
        )
        resp = client.post(
            f"{API_PREFIX}/templates/upload",
            files=[pdf_upload],
            data={"directory": str(tmp_path)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == "test_form.pdf"
        assert data["pdf_path"].endswith(".pdf")

    def test_upload_non_pdf_rejected(self, client):
        import io
        bad_file = ("file", ("notes.txt", io.BytesIO(b"hello"), "text/plain"))
        resp = client.post(f"{API_PREFIX}/templates/upload", files=[bad_file])
        assert resp.status_code == 400
        assert "PDF" in resp.json()["detail"]

    def test_preview_missing_file(self, client):
        resp = client.get(f"{API_PREFIX}/templates/preview", params={"path": "src/inputs/nonexistent.pdf"})
        assert resp.status_code == 404

    def test_directory_traversal_blocked(self, client):
        import io
        pdf = ("file", ("evil.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"))
        resp = client.post(
            f"{API_PREFIX}/templates/upload",
            files=[pdf],
            data={"directory": "/etc"},
        )
        assert resp.status_code == 400
        assert "inside the project" in resp.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════
# Form fill endpoints
# ═══════════════════════════════════════════════════════════════════════════

class TestFormEndpoints:

    def _seed_template(self, client, mock_controller):
        """Helper: create a template and return its ID."""
        resp = client.post(f"{API_PREFIX}/templates/create", json={
            "name": "Employee Form",
            "pdf_path": "src/inputs/employee.pdf",
            "fields": {
                "Employee's name": "string",
                "Employee's email": "string",
            },
        })
        return resp.json()["id"]

    def _seed_input(self, db, status=InputStatus.ready, transcript="The employee is John Doe, email jdoe@ucsc.edu"):
        """Helper: create an Input row directly and return its UUID."""
        record = Input(input_type=InputType.text, status=status, transcript=transcript)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record.input_id

    def test_fill_form_success(self, client, mock_controller, db):
        tpl_id = self._seed_template(client, mock_controller)
        input_id = self._seed_input(db)

        resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": tpl_id,
            "input_id": str(input_id),
        })
        assert resp.status_code == 200

        data = resp.json()
        assert data["id"] is not None
        assert data["template_id"] == tpl_id
        assert data["input_text"] == "The employee is John Doe, email jdoe@ucsc.edu"
        assert data["output_pdf_path"] == "src/outputs/filled_output.pdf"
        mock_controller["form_ctrl"].fill_form.assert_called_once()

        fetched = db.get(FormSubmission, data["id"])
        assert fetched.input_id == input_id

    def test_fill_form_missing_template(self, client, mock_controller):
        resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": 9999,
            "input_id": str(uuid4()),
        })
        assert resp.status_code == 404

    def test_fill_form_missing_input(self, client, mock_controller):
        tpl_id = self._seed_template(client, mock_controller)

        resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": tpl_id,
            "input_id": str(uuid4()),
        })
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "INPUT_NOT_FOUND"

    def test_fill_form_input_transcribing(self, client, mock_controller, db):
        """An input still being transcribed is not usable yet → 409."""
        tpl_id = self._seed_template(client, mock_controller)
        input_id = self._seed_input(db, status=InputStatus.transcribing, transcript=None)

        resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": tpl_id,
            "input_id": str(input_id),
        })
        assert resp.status_code == 409
        body = resp.json()
        assert body["error_code"] == "INPUT_NOT_READY"
        assert body["detail"]["status"] == "transcribing"

    def test_fill_form_input_failed(self, client, mock_controller, db):
        """An input whose transcription failed is never usable → 409."""
        tpl_id = self._seed_template(client, mock_controller)
        input_id = self._seed_input(db, status=InputStatus.failed, transcript=None)

        resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": tpl_id,
            "input_id": str(input_id),
        })
        assert resp.status_code == 409
        body = resp.json()
        assert body["error_code"] == "INPUT_NOT_READY"
        assert body["detail"]["status"] == "failed"

    def test_fill_form_template_file_not_found(self, client, mock_controller, db):
        tpl_id = self._seed_template(client, mock_controller)
        input_id = self._seed_input(db)
        mock_controller["form_ctrl"].fill_form.side_effect = FileNotFoundError("PDF template not found")

        resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": tpl_id,
            "input_id": str(input_id),
        })
        assert resp.status_code == 500
        assert resp.json()["error_code"] == "FORM_FILL_ERROR"
        assert "PDF template not found" in resp.json()["message"]

    def test_fill_form_validates_body(self, client):
        """Missing required fields → 422 with contract envelope."""
        resp = client.post(f"{API_PREFIX}/forms/fill", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error_code"] == "VALIDATION_ERROR"
        assert len(body["validation_errors"]) >= 1
        assert body["validation_errors"][0]["field"] is not None
        assert body["validation_errors"][0]["issue"] is not None

    def test_transcribe_success(self, client, monkeypatch):
        """Audio is forwarded to the whisper sidecar and its text returned."""
        import io
        from unittest.mock import MagicMock

        fake_response = MagicMock()
        fake_response.json.return_value = {"text": "structure fire on main street"}
        fake_response.raise_for_status.return_value = None

        captured = {}

        def fake_post(url, params=None, files=None, timeout=None):
            captured["url"] = url
            captured["params"] = params
            captured["files"] = files
            return fake_response

        monkeypatch.setattr("app.api.routes.forms.requests.post", fake_post)

        audio = ("audio", ("recording.wav", io.BytesIO(b"RIFFfake"), "audio/wav"))
        resp = client.post(f"{API_PREFIX}/forms/transcribe", files=[audio])

        assert resp.status_code == 200
        assert resp.json()["text"] == "structure fire on main street"
        assert captured["url"].endswith("/asr")
        assert "audio_file" in captured["files"]
        assert captured["params"]["output"] == "json"

    def test_list_models(self, client, monkeypatch):
        ""f"{API_PREFIX}/forms/models lists Ollama models and always includes the default."""
        from unittest.mock import MagicMock

        fake_response = MagicMock()
        fake_response.json.return_value = {"models": [{"name": "qwen2.5:3b"}, {"name": "mistral:latest"}]}
        fake_response.raise_for_status.return_value = None
        monkeypatch.setattr("app.api.routes.forms.requests.get", lambda *a, **k: fake_response)
        monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:1.5b")

        resp = client.get(f"{API_PREFIX}/forms/models")
        assert resp.status_code == 200
        body = resp.json()
        assert body["default"] == "qwen2.5:1.5b"
        assert "qwen2.5:1.5b" in body["models"]  # default injected even if not pulled
        assert "qwen2.5:3b" in body["models"]

    def test_list_models_ollama_down(self, client, monkeypatch):
        """If Ollama is unreachable, still return the default alone."""
        import requests

        def boom(*a, **k):
            raise requests.exceptions.ConnectionError("down")

        monkeypatch.setattr("app.api.routes.forms.requests.get", boom)
        monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:1.5b")

        resp = client.get(f"{API_PREFIX}/forms/models")
        assert resp.status_code == 200
        assert resp.json()["models"] == ["qwen2.5:1.5b"]

    def test_fill_form_passes_model_override(self, client, mock_controller, db):
        """A `model` in the request reaches Controller.fill_form but isn't persisted."""
        tpl_id = self._seed_template(client, mock_controller)
        input_id = self._seed_input(db, transcript="John Doe")
        resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": tpl_id,
            "input_id": str(input_id),
            "model": "qwen2.5:3b",
        })
        assert resp.status_code == 200
        _, kwargs = mock_controller["form_ctrl"].fill_form.call_args
        assert kwargs["model"] == "qwen2.5:3b"

    def test_transcribe_service_unavailable(self, client, monkeypatch):
        """A down whisper service surfaces as a 503, not a 500."""
        import io

        import requests

        def fake_post(*args, **kwargs):
            raise requests.exceptions.ConnectionError("no service")

        monkeypatch.setattr("app.api.routes.forms.requests.post", fake_post)

        audio = ("audio", ("recording.wav", io.BytesIO(b"data"), "audio/wav"))
        resp = client.post(f"{API_PREFIX}/forms/transcribe", files=[audio])
        assert resp.status_code == 503


# ═══════════════════════════════════════════════════════════════════════════
# End-to-end pipeline
# ═══════════════════════════════════════════════════════════════════════════

class TestE2EPipeline:
    """
    Full pipeline: upload PDF → create template → fill form → verify DB state.
    This is the critical path that the product depends on.
    """

    def test_full_flow(self, client, mock_controller, pdf_upload, tmp_path, monkeypatch, db):
        # -- Step 1: Upload a PDF --
        monkeypatch.setattr("app.services.template.PROJECT_ROOT", tmp_path)
        upload_resp = client.post(
            f"{API_PREFIX}/templates/upload",
            files=[pdf_upload],
            data={"directory": str(tmp_path)},
        )
        assert upload_resp.status_code == 200
        uploaded_path = upload_resp.json()["pdf_path"]
        assert uploaded_path.endswith(".pdf")

        # -- Step 2: Create a template from the uploaded PDF --
        create_resp = client.post(f"{API_PREFIX}/templates/create", json={
            "name": "Incident Report",
            "pdf_path": uploaded_path,
            "fields": {
                "Officer name": "string",
                "Badge number": "string",
                "Incident date": "string",
                "Location": "string",
                "Description": "string",
            },
        })
        assert create_resp.status_code == 200
        template_id = create_resp.json()["id"]
        assert template_id is not None

        # -- Step 3: Verify template appears in list --
        list_resp = client.get(f"{API_PREFIX}/templates")
        assert list_resp.status_code == 200
        templates = list_resp.json()
        assert any(t["id"] == template_id for t in templates)

        # -- Step 4: Fill the form --
        input_record = Input(
            input_type=InputType.text,
            status=InputStatus.ready,
            transcript=(
                "Officer Jane Smith, badge 4521. On January 15 2025 at "
                "123 Main St, a structure fire was reported. Two engines "
                "responded, fire contained within 45 minutes."
            ),
        )
        db.add(input_record)
        db.commit()
        db.refresh(input_record)

        fill_resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": template_id,
            "input_id": str(input_record.input_id),
        })
        assert fill_resp.status_code == 200
        fill_data = fill_resp.json()
        assert fill_data["template_id"] == template_id
        assert fill_data["output_pdf_path"] == "src/outputs/filled_output.pdf"

        # -- Step 5: Verify DB state --
        db_templates = list(db.exec(select(Template)))
        assert len(db_templates) == 1

        db_forms = list(db.exec(select(FormSubmission)))
        assert len(db_forms) == 1
        assert db_forms[0].template_id == template_id
        assert db_forms[0].input_id == input_record.input_id
        assert "Jane Smith" in db_forms[0].input_text
