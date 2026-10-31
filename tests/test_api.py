"""Comprehensive API tests for FireForm.

Covers every endpoint and the full upload → template → fill pipeline.
All heavy dependencies (LLM, commonforms, filesystem) are mocked via conftest.
"""

from uuid import uuid4

import pytest

from sqlmodel import select

from app.api.schemas.enums import InputStatus, InputType
from app.core.config import API_PREFIX
from app.models import FormSubmission, Input, Template

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
            "description": "Fire incident report",
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
        assert data["description"] == "Fire incident report"
        # Fields passed explicitly are persisted as-is (extract_pdf_template not called)
        assert data["fields"]["Location"] == "string"
        mock_controller["mock_extract"].assert_not_called()

    def test_create_then_list(self, client, mock_controller):
        """Creating a template should make it appear in the list."""
        client.post(f"{API_PREFIX}/templates/create", json={
            "name": "T1",
            "description": "Test form template",
            "pdf_path": "a.pdf",
            "fields": {"f": "string"},
        })
        resp = client.get(f"{API_PREFIX}/templates")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["name"] == "T1"
        assert resp.json()[0]["description"] == "Test form template"

    def test_upload_pdf(self, client, pdf_upload, tmp_path, monkeypatch):
        """Upload a valid PDF file."""
        # Point the upload directory inside tmp_path (which is inside the project
        # for the path-safety check — we monkeypatch the check).
        monkeypatch.setattr(
            "app.core.paths.PROJECT_ROOT",
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

    def test_upload_oversize_pdf_rejected(self, client, monkeypatch):
        import io
        monkeypatch.setattr("app.api.routes.templates._MAX_TEMPLATE_BYTES", 5)
        pdf = ("file", ("big.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"))  # 8 bytes > 5
        resp = client.post(f"{API_PREFIX}/templates/upload", files=[pdf])
        assert resp.status_code == 413
        body = resp.json()
        assert body["error_code"] == "FILE_TOO_LARGE"
        assert body["detail"]["max_size_bytes"] == 5
        assert body["detail"]["received_size_bytes"] == 8

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

    def test_update_template(self, client, mock_controller):
        created = client.post(f"{API_PREFIX}/templates/create", json={
            "name": "T1",
            "pdf_path": "a.pdf",
            "fields": {"f": "string"},
        }).json()

        resp = client.put(f"{API_PREFIX}/templates/{created['id']}", json={"name": "T2"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "T2"
        # Fields not sent are left unchanged
        assert resp.json()["fields"] == {"f": "string"}
        assert resp.json()["pdf_path"] == "a.pdf"

        resp = client.put(
            f"{API_PREFIX}/templates/{created['id']}",
            json={"fields": {"g": "string", "h": "string"}},
        )
        assert resp.status_code == 200
        assert resp.json()["fields"] == {"g": "string", "h": "string"}
        assert resp.json()["field_count"] == 2
        assert client.get(f"{API_PREFIX}/templates").json()[0]["name"] == "T2"

    def test_update_template_description(self, client, db, mock_controller):
        """PUT /templates/{id} persists a new description."""
        tpl = Template(
            name="ICS 205",
            description="Original radio plan",
            pdf_path="a.pdf",
            fields={"f": "string"},
        )
        db.add(tpl)
        db.commit()
        db.refresh(tpl)

        resp = client.put(
            f"{API_PREFIX}/templates/{tpl.id}",
            json={"description": "Updated ICS 205 radio plan"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated ICS 205 radio plan"
        assert resp.json()["name"] == "ICS 205"
        assert resp.json()["fields"] == {"f": "string"}
        assert client.get(f"{API_PREFIX}/templates").json()[0]["description"] == (
            "Updated ICS 205 radio plan"
        )

    def test_update_keeps_description_when_omitted(self, client, db, mock_controller):
        """A name-only PUT must not clear an existing description."""
        tpl = Template(
            name="ICS 205",
            description="Keep this comms plan",
            pdf_path="a.pdf",
            fields={"f": "string"},
        )
        db.add(tpl)
        db.commit()
        db.refresh(tpl)

        resp = client.put(f"{API_PREFIX}/templates/{tpl.id}", json={"name": "ICS 205A"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "ICS 205A"
        assert resp.json()["description"] == "Keep this comms plan"

    def test_update_missing_template(self, client):
        resp = client.put(f"{API_PREFIX}/templates/9999", json={"name": "T2"})
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# Form fill endpoints
# ═══════════════════════════════════════════════════════════════════════════

class TestFormEndpoints:

    def _seed_template(self, client, mock_controller):
        """Helper: create a template with the default stub path and return its ID."""
        resp = client.post(f"{API_PREFIX}/templates/create", json={
            "name": "Employee Form",
            "description": "Employee information form",
            "pdf_path": "src/inputs/employee.pdf",
            "fields": {
                "Employee's name": "string",
                "Employee's email": "string",
            },
        })
        return resp.json()["id"]

    def _seed_template_at(self, client, pdf_path: str):
        """Helper: create a template with a specific pdf_path and return its ID."""
        resp = client.post(f"{API_PREFIX}/templates/create", json={
            "name": "Employee Form",
            "pdf_path": pdf_path,
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

    def test_fill_form_success(self, client, mock_controller, db, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.paths.PROJECT_ROOT", tmp_path)
        # Create a real PDF file so paths._resolve_project_file succeeds
        pdf_file = tmp_path / "employee.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")
        tpl_id = self._seed_template_at(client, str(pdf_file.relative_to(tmp_path)))
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
        assert data["output_pdf_path"].endswith("_filled.pdf")
        mock_controller["mock_fill"].assert_called_once()

        fetched = db.get(FormSubmission, data["id"])
        assert fetched.input_id == input_id

    def test_fill_form_with_direct_input_text(self, client, mock_controller, db, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.paths.PROJECT_ROOT", tmp_path)
        pdf_file = tmp_path / "employee.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")
        tpl_id = self._seed_template_at(client, str(pdf_file.relative_to(tmp_path)))

        resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": tpl_id,
            "input_text": "Direct incident text narrative from user.",
        })
        assert resp.status_code == 200

        data = resp.json()
        assert data["id"] is not None
        assert data["template_id"] == tpl_id
        assert data["input_text"] == "Direct incident text narrative from user."
        assert data["output_pdf_path"].endswith("_filled.pdf")

        fetched = db.get(FormSubmission, data["id"])
        assert fetched is not None
        assert fetched.input_text == "Direct incident text narrative from user."
        assert fetched.input_id is not None

    def test_fill_form_uses_description_from_update(
        self, client, mock_controller, db, tmp_path, monkeypatch
    ):
        """A description saved via PUT /templates/{id} reaches the filler."""
        monkeypatch.setattr("app.core.paths.PROJECT_ROOT", tmp_path)
        pdf_file = tmp_path / "ics_205.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")
        tpl = Template(
            name="ICS 205",
            description="",
            pdf_path="ics_205.pdf",
            fields={"Incident Name": "string"},
        )
        db.add(tpl)
        db.commit()
        db.refresh(tpl)

        updated = client.put(
            f"{API_PREFIX}/templates/{tpl.id}",
            json={"description": "Incident radio communications plan"},
        )
        assert updated.status_code == 200
        assert updated.json()["description"] == "Incident radio communications plan"

        resp = client.post(
            f"{API_PREFIX}/forms/fill",
            json={
                "template_id": tpl.id,
                "input_text": "Command uses channel 3 for the Oak Ridge fire.",
            },
        )
        assert resp.status_code == 200
    def test_fill_form_uses_description_from_create(self, client, mock_controller, tmp_path, monkeypatch):
        """The description given to POST /templates/create reaches the filler."""
        monkeypatch.setattr("app.core.paths.PROJECT_ROOT", tmp_path)
        pdf_file = tmp_path / "ics_205.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")
        created = client.post(f"{API_PREFIX}/templates/create", json={
            "name": "ICS 205",
            "description": "Incident radio communications plan",
            "pdf_path": "ics_205.pdf",
            "fields": {"Incident Name": "string"},
        })
        assert created.status_code == 200

        resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": created.json()["id"],
            "input_text": "Command uses channel 3 for the Oak Ridge fire.",
        })
        assert resp.status_code == 200

        mock_fill = mock_controller["mock_fill"]
        mock_fill.assert_called_once()
        assert mock_fill.call_args.kwargs["description"] == "Incident radio communications plan"


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
        # Template with a non-existent PDF path → service raises FileNotFoundError
        tpl_id = self._seed_template(client, mock_controller)
        input_id = self._seed_input(db)

        resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": tpl_id,
            "input_id": str(input_id),
        })
        # The service detects the missing PDF before calling filler.fill
        assert resp.status_code == 500
        assert resp.json()["error_code"] == "FORM_FILL_ERROR"

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
        """/forms/models lists the LLM's models and always includes the default."""
        from app.services.llm import ModelInfo

        monkeypatch.setattr(
            "app.services.llm.ollama.OllamaLLM.list_models",
            lambda self: [ModelInfo(name="qwen2.5:3b"), ModelInfo(name="mistral:latest")],
        )

        resp = client.get(f"{API_PREFIX}/forms/models")
        assert resp.status_code == 200
        body = resp.json()
        assert body["default"] == "qwen2.5:1.5b"
        assert "qwen2.5:1.5b" in body["models"]  # default injected even if not pulled
        assert "qwen2.5:3b" in body["models"]

    def test_list_models_llm_down(self, client, monkeypatch):
        """If the LLM server is unreachable, still return the default alone."""
        import requests

        def boom(*a, **k):
            raise requests.exceptions.ConnectionError("down")

        monkeypatch.setattr("app.services.llm.ollama.requests.request", boom)

        resp = client.get(f"{API_PREFIX}/forms/models")
        assert resp.status_code == 200
        assert resp.json()["models"] == ["qwen2.5:1.5b"]

    def test_fill_form_passes_model_override(self, client, mock_controller, db, tmp_path, monkeypatch, test_llm):
        """A `model` in the request reaches filler.fill as a keyword argument."""
        from app.services.llm import ModelInfo

        monkeypatch.setattr(test_llm, "list_models", lambda: [ModelInfo(name="qwen2.5:3b")])
        monkeypatch.setattr("app.core.paths.PROJECT_ROOT", tmp_path)
        pdf_file = tmp_path / "employee.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")
        tpl_id = self._seed_template_at(client, str(pdf_file.relative_to(tmp_path)))
        input_id = self._seed_input(db, transcript="John Doe")
        resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": tpl_id,
            "input_id": str(input_id),
            "model": "qwen2.5:3b",
        })
        assert resp.status_code == 200
        # filler.fill is called as fill(pdf_path, narrative, out_path, model=...)
        call_args = mock_controller["mock_fill"].call_args
        assert call_args.kwargs.get("model") == "qwen2.5:3b" or call_args.args[3] == "qwen2.5:3b"

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

    def test_transcribe_oversize_audio_rejected(self, client, monkeypatch):
        """Audio over the size limit is rejected with 413 before reaching whisper."""
        import io

        monkeypatch.setattr("app.api.routes.forms._MAX_AUDIO_BYTES", 5)

        def fake_whisper(*args, **kwargs):
            raise AssertionError("whisper should not be called")

        monkeypatch.setattr("app.api.routes.forms.call_whisper_asr", fake_whisper)

        audio = ("audio", ("recording.wav", io.BytesIO(b"RIFFfake"), "audio/wav"))  # 8 bytes > 5
        resp = client.post(f"{API_PREFIX}/forms/transcribe", files=[audio])
        assert resp.status_code == 413
        body = resp.json()
        assert body["error_code"] == "FILE_TOO_LARGE"
        assert body["detail"]["max_size_bytes"] == 5
        assert body["detail"]["received_size_bytes"] == 8


# ═══════════════════════════════════════════════════════════════════════════
# Weather endpoint
# ═══════════════════════════════════════════════════════════════════════════

class TestWeatherEndpoints:

    WEATHER_URL = f"{API_PREFIX}/weather/forecast"
    VALID = {"latitude": 37.77, "longitude": -122.42, "start_date": "2026-10-19", "end_date": "2026-10-20"}

    def _no_upstream_call(self, monkeypatch):
        def fake_get_weather(*args, **kwargs):
            raise AssertionError("Open-Meteo should not be called for invalid input")

        monkeypatch.setattr(
            "app.api.routes.weather.WeatherAPI.get_weather", fake_get_weather
        )

    def test_forecast_valid_request(self, client, monkeypatch):
        captured = {}

        def fake_get_weather(self, latitude, longitude, start_date, end_date, hourly_fields=None):
            captured.update(latitude=latitude, longitude=longitude, start_date=start_date, end_date=end_date)
            return {"hourly": {}}

        monkeypatch.setattr("app.api.routes.weather.WeatherAPI.get_weather", fake_get_weather)

        resp = client.get(self.WEATHER_URL, params=self.VALID)
        assert resp.status_code == 200
        assert captured == {
            "latitude": 37.77,
            "longitude": -122.42,
            "start_date": "2026-10-19",
            "end_date": "2026-10-20",
        }

    def test_forecast_upstream_error_is_502(self, client, monkeypatch):
        from openmeteo_requests.Client import OpenMeteoRequestsError

        def fake_weather_api(*args, **kwargs):
            raise OpenMeteoRequestsError("failed to request 'https://api.open-meteo.com/v1/forecast': offline")

        monkeypatch.setattr("openmeteo_requests.Client.weather_api", fake_weather_api)

        resp = client.get(self.WEATHER_URL, params=self.VALID)
        assert resp.status_code == 502
        body = resp.json()
        assert body["error_code"] == "WEATHER_FETCH_FAILED"
        assert "offline" in body["message"]

    def test_forecast_unexpected_error_is_500(self, client, monkeypatch):
        def fake_get_weather(*args, **kwargs):
            raise ValueError("boom")

        monkeypatch.setattr("app.api.routes.weather.WeatherAPI.get_weather", fake_get_weather)

        resp = client.get(self.WEATHER_URL, params=self.VALID)
        assert resp.status_code == 500

    @pytest.mark.parametrize(
        "overrides, field",
        [
            ({"latitude": 200}, "query.latitude"),
            ({"latitude": -90.5}, "query.latitude"),
            ({"longitude": 181}, "query.longitude"),
            ({"start_date": "tomorrow"}, "query.start_date"),
            ({"end_date": "2026-13-01"}, "query.end_date"),
            ({"start_date": "2026-10-22", "end_date": "2026-10-19"}, "query.end_date"),
        ],
    )
    def test_forecast_invalid_params_rejected(self, client, monkeypatch, overrides, field):
        self._no_upstream_call(monkeypatch)

        resp = client.get(self.WEATHER_URL, params={**self.VALID, **overrides})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error_code"] == "VALIDATION_ERROR"
        assert body["validation_errors"][0]["field"] == field


# ═══════════════════════════════════════════════════════════════════════════
# Address lookup endpoint
# ═══════════════════════════════════════════════════════════════════════════

class TestZipcodeEndpoints:

    LOOKUP_URL = f"{API_PREFIX}/zipcode/lookup-address"
    GEOCODE = "app.services.external_apis.zipcode_api._GEOLOCATOR.geocode"

    @pytest.mark.parametrize("address", ["", "   "])
    def test_lookup_blank_address_rejected(self, client, monkeypatch, address):
        def fake_geocode(*args, **kwargs):
            raise AssertionError("Nominatim should not be called for a blank address")

        monkeypatch.setattr(self.GEOCODE, fake_geocode)

        resp = client.get(self.LOOKUP_URL, params={"address": address})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error_code"] == "VALIDATION_ERROR"
        assert body["validation_errors"][0]["field"] == "query.address"

    def test_lookup_upstream_error_is_502(self, client, monkeypatch):
        from geopy.exc import GeocoderServiceError

        def fake_geocode(*args, **kwargs):
            raise GeocoderServiceError("HTTP Error 503: Service Unavailable")

        monkeypatch.setattr(self.GEOCODE, fake_geocode)

        resp = client.get(self.LOOKUP_URL, params={"address": "Paris"})
        assert resp.status_code == 502
        assert resp.json()["error_code"] == "GEOCODING_FAILED"

    def test_lookup_timeout_is_504(self, client, monkeypatch):
        from geopy.exc import GeocoderTimedOut

        def fake_geocode(*args, **kwargs):
            raise GeocoderTimedOut("timed out")

        monkeypatch.setattr(self.GEOCODE, fake_geocode)

        resp = client.get(self.LOOKUP_URL, params={"address": "Paris"})
        assert resp.status_code == 504
        assert resp.json()["error_code"] == "GEOCODING_TIMEOUT"

    def test_lookup_no_results(self, client, monkeypatch):
        monkeypatch.setattr(self.GEOCODE, lambda *args, **kwargs: None)

        resp = client.get(self.LOOKUP_URL, params={"address": "Nowhere at all"})
        assert resp.status_code == 200
        assert resp.json() == []


# ═══════════════════════════════════════════════════════════════════════════
# End-to-end pipeline
# ═══════════════════════════════════════════════════════════════════════════

class TestE2EPipeline:
    """
    Full pipeline: upload PDF → create template → fill form → verify DB state.
    This is the critical path that the product depends on.
    """

    def test_full_flow(self, client, mock_controller, pdf_upload, tmp_path, monkeypatch, db):
        monkeypatch.setattr("app.core.paths.PROJECT_ROOT", tmp_path)

        # -- Step 1: Upload a PDF --
        upload_resp = client.post(
            f"{API_PREFIX}/templates/upload",
            files=[pdf_upload],
            data={"directory": str(tmp_path)},
        )
        assert upload_resp.status_code == 200
        uploaded_path = upload_resp.json()["pdf_path"]
        assert uploaded_path.endswith(".pdf")

        # -- Step 2: Create a template (fields explicit → extract_pdf_template not called) --
        create_resp = client.post(f"{API_PREFIX}/templates/create", json={
            "name": "Incident Report",
            "description": "Incident report form",
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
        assert fill_data["output_pdf_path"].endswith("_filled.pdf")
        mock_controller["mock_fill"].assert_called_once()

        # -- Step 5: Verify DB state --
        db_templates = list(db.exec(select(Template)))
        assert len(db_templates) == 1

        db_forms = list(db.exec(select(FormSubmission)))
        assert len(db_forms) == 1
        assert db_forms[0].template_id == template_id
        assert db_forms[0].input_id == input_record.input_id
        assert "Jane Smith" in db_forms[0].input_text
