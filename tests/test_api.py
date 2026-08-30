"""Comprehensive API tests for FireForm.

Covers every endpoint and the full upload → template → fill pipeline.
All heavy dependencies (LLM, commonforms, filesystem) are mocked via conftest.
"""

from sqlmodel import select

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

        sub = FormSubmission(
            template_id=tpl.id,
            input_text="John Doe, firefighter",
            output_pdf_path="src/outputs/filled.pdf",
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)

        fetched = db.get(FormSubmission, sub.id)
        assert fetched is not None
        assert fetched.template_id == tpl.id
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
        """Contract registry list is empty until a template is registered."""
        resp = client.get(f"{API_PREFIX}/templates")
        assert resp.status_code == 200
        assert resp.json() == []


# ═══════════════════════════════════════════════════════════════════════════
# Form fill endpoints (legacy pipeline — templates seeded directly in the DB
# since the /templates/create endpoint was removed in the contract migration)
# ═══════════════════════════════════════════════════════════════════════════

class TestFormEndpoints:

    def test_fill_form_success(self, client, mock_controller, seed_template):
        tpl_id = seed_template()

        resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": tpl_id,
            "input_text": "The employee is John Doe, email jdoe@ucsc.edu",
        })
        assert resp.status_code == 200

        data = resp.json()
        assert data["id"] is not None
        assert data["template_id"] == tpl_id
        assert data["output_pdf_path"] == "src/outputs/filled_output.pdf"
        mock_controller["form_ctrl"].fill_form.assert_called_once()

    def test_fill_form_missing_template(self, client, mock_controller):
        resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": 9999,
            "input_text": "some text",
        })
        assert resp.status_code == 404

    def test_fill_form_template_file_not_found(self, client, mock_controller, seed_template):
        tpl_id = seed_template()
        mock_controller["form_ctrl"].fill_form.side_effect = FileNotFoundError("PDF template not found")

        resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": tpl_id,
            "input_text": "some text",
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

        monkeypatch.setattr("app.services.whisper.requests.post", fake_post)

        audio = ("audio", ("recording.wav", io.BytesIO(b"RIFFfake"), "audio/wav"))
        resp = client.post(f"{API_PREFIX}/forms/transcribe", files=[audio])

        assert resp.status_code == 200
        assert resp.json()["text"] == "structure fire on main street"
        assert captured["url"].endswith("/asr")
        assert "audio_file" in captured["files"]
        assert captured["params"]["output"] == "json"

    def test_list_models(self, client, monkeypatch):
        ""f"{API_PREFIX}/forms/models lists what the provider serves, default marked."""
        from app.services.llm.models import ModelInfo

        monkeypatch.setattr(
            "app.api.routes.forms.llm.list_models",
            lambda: [
                ModelInfo(name="qwen2.5:1.5b", default=True),
                ModelInfo(name="qwen2.5:3b"),
                ModelInfo(name="mistral:latest"),
            ],
        )

        resp = client.get(f"{API_PREFIX}/forms/models")
        assert resp.status_code == 200
        body = resp.json()
        assert body["default"] == "qwen2.5:1.5b"
        assert body["models"] == ["qwen2.5:1.5b", "qwen2.5:3b", "mistral:latest"]

    def test_list_models_provider_down(self, client, monkeypatch):
        """A provider that will not list them still yields the configured model."""
        from app.services.llm.models import ModelInfo

        monkeypatch.setattr(
            "app.api.routes.forms.llm.list_models",
            lambda: [ModelInfo(name="qwen2.5:1.5b", default=True)],
        )

        resp = client.get(f"{API_PREFIX}/forms/models")
        assert resp.status_code == 200
        assert resp.json()["models"] == ["qwen2.5:1.5b"]

    def test_fill_form_passes_model_override(self, client, mock_controller, seed_template):
        """A `model` in the request reaches Controller.fill_form but isn't persisted."""
        tpl_id = seed_template()
        resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": tpl_id,
            "input_text": "John Doe",
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

        monkeypatch.setattr("app.services.whisper.requests.post", fake_post)

        audio = ("audio", ("recording.wav", io.BytesIO(b"data"), "audio/wav"))
        resp = client.post(f"{API_PREFIX}/forms/transcribe", files=[audio])
        assert resp.status_code == 503


# ═══════════════════════════════════════════════════════════════════════════
# End-to-end pipeline
# ═══════════════════════════════════════════════════════════════════════════

class TestE2EPipeline:
    """
    Legacy fill pipeline: seed template → fill form → verify DB state.
    Template registration via API was removed in the contract migration, so the
    template is seeded directly in the DB.
    """

    def test_full_flow(self, client, mock_controller, seed_template, db):
        # -- Step 1: Seed a template --
        template_id = seed_template(
            name="Incident Report",
            pdf_path="src/inputs/incident.pdf",
            fields={
                "Officer name": "string",
                "Badge number": "string",
                "Incident date": "string",
                "Location": "string",
                "Description": "string",
            },
        )
        assert template_id is not None

        # -- Step 2: Fill the form --
        fill_resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": template_id,
            "input_text": (
                "Officer Jane Smith, badge 4521. On January 15 2025 at "
                "123 Main St, a structure fire was reported. Two engines "
                "responded, fire contained within 45 minutes."
            ),
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
        assert "Jane Smith" in db_forms[0].input_text
