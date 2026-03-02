"""
Tests for the async/streaming form-fill endpoints:

  POST /forms/fill/stream  — SSE streaming (field-by-field progress)
  POST /forms/fill/async   — background job (returns 202 + job_id)
  GET  /forms/jobs/{id}    — job status polling

Also covers unit tests for the new LLM async helpers and Filler.fill_form_with_data().
"""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.llm import LLM
from src.filler import Filler


# ── Constants ─────────────────────────────────────────────────────────────────

SAMPLE_FIELDS = {
    "reporting_officer": "string",
    "incident_location": "string",
    "victim_names": "string",
}

SAMPLE_INPUT = (
    "Officer Smith reporting from 456 Oak Street. "
    "Victim Jane Doe was treated on scene."
)


# ── Async generator mocks ─────────────────────────────────────────────────────

async def _mock_stream_all_high(self):
    """All fields extracted at high confidence on first pass."""
    yield {"field": "reporting_officer", "value": "Smith", "confidence": "high", "phase": "initial"}
    yield {"field": "incident_location", "value": "456 Oak Street", "confidence": "high", "phase": "initial"}
    yield {"field": "victim_names", "value": "Jane Doe", "confidence": "high", "phase": "initial"}


async def _mock_stream_with_retry(self):
    """First pass misses reporting_officer; retry recovers it at medium confidence."""
    yield {"field": "reporting_officer", "value": None, "confidence": "low", "phase": "initial"}
    yield {"field": "incident_location", "value": "456 Oak Street", "confidence": "high", "phase": "initial"}
    yield {"field": "victim_names", "value": "Jane Doe", "confidence": "high", "phase": "initial"}
    # retry pass
    yield {"field": "reporting_officer", "value": "Smith", "confidence": "medium", "phase": "retry"}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def template_id(client):
    """Inserts a Template row into the test DB and returns its integer id."""
    with patch("api.routes.templates.Controller") as MockCtrl:
        MockCtrl.return_value.create_template.return_value = "/tmp/incident_template.pdf"
        resp = client.post(
            "/templates/create",
            json={
                "name": "Incident Report",
                "pdf_path": "/tmp/incident.pdf",
                "fields": SAMPLE_FIELDS,
            },
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


# ── POST /forms/fill/stream ───────────────────────────────────────────────────

def test_stream_returns_event_stream_content_type(client, template_id):
    with patch.object(LLM, "async_extract_all_streaming", _mock_stream_all_high), \
         patch.object(Filler, "fill_form_with_data", return_value="/tmp/filled.pdf"):
        resp = client.post(
            "/forms/fill/stream",
            json={"template_id": template_id, "input_text": SAMPLE_INPUT},
        )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]


def test_stream_yields_one_event_per_field(client, template_id):
    with patch.object(LLM, "async_extract_all_streaming", _mock_stream_all_high), \
         patch.object(Filler, "fill_form_with_data", return_value="/tmp/filled.pdf"):
        resp = client.post(
            "/forms/fill/stream",
            json={"template_id": template_id, "input_text": SAMPLE_INPUT},
        )

    data_lines = [l for l in resp.text.split("\n") if l.startswith("data:")]
    payloads = [json.loads(l[5:].strip()) for l in data_lines]
    field_events = [p for p in payloads if "field" in p]
    extracted_fields = {e["field"] for e in field_events}
    assert extracted_fields == set(SAMPLE_FIELDS.keys())


def test_stream_complete_event_is_last(client, template_id):
    with patch.object(LLM, "async_extract_all_streaming", _mock_stream_all_high), \
         patch.object(Filler, "fill_form_with_data", return_value="/tmp/filled.pdf"):
        resp = client.post(
            "/forms/fill/stream",
            json={"template_id": template_id, "input_text": SAMPLE_INPUT},
        )

    data_lines = [l for l in resp.text.split("\n") if l.startswith("data:")]
    payloads = [json.loads(l[5:].strip()) for l in data_lines]
    complete_events = [p for p in payloads if p.get("status") == "complete"]
    assert len(complete_events) == 1
    assert "submission_id" in complete_events[0]
    assert complete_events[0]["output_pdf_path"] == "/tmp/filled.pdf"


def test_stream_all_field_events_carry_confidence_and_phase(client, template_id):
    with patch.object(LLM, "async_extract_all_streaming", _mock_stream_all_high), \
         patch.object(Filler, "fill_form_with_data", return_value="/tmp/filled.pdf"):
        resp = client.post(
            "/forms/fill/stream",
            json={"template_id": template_id, "input_text": SAMPLE_INPUT},
        )

    data_lines = [l for l in resp.text.split("\n") if l.startswith("data:")]
    payloads = [json.loads(l[5:].strip()) for l in data_lines]
    for event in payloads:
        if "field" in event:
            assert event["confidence"] in ("high", "medium", "low"), event
            assert event["phase"] in ("initial", "retry"), event


def test_stream_retry_events_are_visible_to_client(client, template_id):
    with patch.object(LLM, "async_extract_all_streaming", _mock_stream_with_retry), \
         patch.object(Filler, "fill_form_with_data", return_value="/tmp/filled.pdf"):
        resp = client.post(
            "/forms/fill/stream",
            json={"template_id": template_id, "input_text": SAMPLE_INPUT},
        )

    data_lines = [l for l in resp.text.split("\n") if l.startswith("data:")]
    payloads = [json.loads(l[5:].strip()) for l in data_lines]
    retry_events = [p for p in payloads if p.get("phase") == "retry"]
    assert len(retry_events) >= 1
    assert retry_events[0]["confidence"] == "medium"
    assert retry_events[0]["field"] == "reporting_officer"


def test_stream_404_on_unknown_template(client):
    resp = client.post(
        "/forms/fill/stream",
        json={"template_id": 999999, "input_text": SAMPLE_INPUT},
    )
    assert resp.status_code == 404


# ── POST /forms/fill/async ────────────────────────────────────────────────────

def test_async_fill_returns_202(client, template_id):
    # Mock the background task to prevent it from using the production engine
    with patch("api.routes.forms._run_fill_job", new_callable=AsyncMock):
        resp = client.post(
            "/forms/fill/async",
            json={"template_id": template_id, "input_text": SAMPLE_INPUT},
        )
    assert resp.status_code == 202


def test_async_fill_response_contains_job_id(client, template_id):
    with patch("api.routes.forms._run_fill_job", new_callable=AsyncMock):
        resp = client.post(
            "/forms/fill/async",
            json={"template_id": template_id, "input_text": SAMPLE_INPUT},
        )
    body = resp.json()
    assert "job_id" in body
    assert isinstance(body["job_id"], str)
    assert len(body["job_id"]) > 0


def test_async_fill_initial_status_is_pending(client, template_id):
    with patch("api.routes.forms._run_fill_job", new_callable=AsyncMock):
        resp = client.post(
            "/forms/fill/async",
            json={"template_id": template_id, "input_text": SAMPLE_INPUT},
        )
    assert resp.json()["status"] == "pending"


def test_async_fill_404_on_unknown_template(client):
    resp = client.post(
        "/forms/fill/async",
        json={"template_id": 999999, "input_text": SAMPLE_INPUT},
    )
    assert resp.status_code == 404


# ── GET /forms/jobs/{job_id} ──────────────────────────────────────────────────

def test_get_job_status_returns_200(client, template_id):
    with patch("api.routes.forms._run_fill_job", new_callable=AsyncMock):
        submit = client.post(
            "/forms/fill/async",
            json={"template_id": template_id, "input_text": SAMPLE_INPUT},
        )
    job_id = submit.json()["job_id"]
    resp = client.get(f"/forms/jobs/{job_id}")
    assert resp.status_code == 200


def test_get_job_status_correct_fields(client, template_id):
    with patch("api.routes.forms._run_fill_job", new_callable=AsyncMock):
        submit = client.post(
            "/forms/fill/async",
            json={"template_id": template_id, "input_text": SAMPLE_INPUT},
        )
    job_id = submit.json()["job_id"]
    body = client.get(f"/forms/jobs/{job_id}").json()

    assert body["id"] == job_id
    assert body["template_id"] == template_id
    assert body["input_text"] == SAMPLE_INPUT
    assert body["status"] in ("pending", "running", "complete", "failed")


def test_get_job_status_404_unknown_id(client):
    resp = client.get("/forms/jobs/does-not-exist-at-all")
    assert resp.status_code == 404


# ── Unit: LLM._build_targeted_prompt ─────────────────────────────────────────

def test_targeted_prompt_contains_field_name():
    llm = LLM(transcript_text="Smith at Oak Street", target_fields=SAMPLE_FIELDS)
    prompt = llm._build_targeted_prompt("reporting_officer")
    assert "reporting_officer" in prompt


def test_targeted_prompt_contains_transcript():
    llm = LLM(transcript_text="Smith at Oak Street", target_fields=SAMPLE_FIELDS)
    prompt = llm._build_targeted_prompt("reporting_officer")
    assert "Smith at Oak Street" in prompt


def test_targeted_prompt_instructs_minus_one_fallback():
    llm = LLM(transcript_text="x", target_fields={"f": "string"})
    prompt = llm._build_targeted_prompt("f")
    assert "-1" in prompt


# ── Unit: Filler.fill_form_with_data ─────────────────────────────────────────

def test_fill_form_with_data_returns_filled_pdf_path():
    filler = Filler()
    mock_annot = MagicMock()
    mock_annot.Subtype = "/Widget"
    mock_annot.T = "field1"
    mock_annot.Rect = ["0.0", "100.0", "200.0", "120.0"]
    mock_page = MagicMock()
    mock_page.Annots = [mock_annot]
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]

    with patch("src.filler.PdfReader", return_value=mock_pdf), \
         patch("src.filler.PdfWriter") as MockWriter:
        MockWriter.return_value.write = MagicMock()
        result = filler.fill_form_with_data("/fake/form.pdf", {"field1": "TestValue"})

    assert result.endswith("_filled.pdf")
    assert mock_annot.V == "TestValue"


def test_fill_form_with_data_handles_none_values():
    """None values in data dict should produce empty string in the PDF, not crash."""
    filler = Filler()
    mock_annot = MagicMock()
    mock_annot.Subtype = "/Widget"
    mock_annot.T = "field1"
    mock_annot.Rect = ["0.0", "100.0", "200.0", "120.0"]
    mock_page = MagicMock()
    mock_page.Annots = [mock_annot]
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]

    with patch("src.filler.PdfReader", return_value=mock_pdf), \
         patch("src.filler.PdfWriter") as MockWriter:
        MockWriter.return_value.write = MagicMock()
        result = filler.fill_form_with_data("/fake/form.pdf", {"field1": None})

    assert mock_annot.V == ""
    assert result.endswith("_filled.pdf")
