"""
Tests for /forms endpoints.
Closes #165, #205, #163
"""

import pytest
from unittest.mock import patch
from api.db.models import Template, FormSubmission
from datetime import datetime


# ── helpers ───────────────────────────────────────────────────────────────────

def make_template(db_session):
    t = Template(
        name="Test Form",
        fields={"JobTitle": "Job Title"},
        pdf_path="/tmp/test.pdf",
        created_at=datetime.utcnow(),
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t.id


def make_submission(db_session, template_id, output_path="/tmp/filled.pdf"):
    s = FormSubmission(
        template_id=template_id,
        input_text="John Smith is a firefighter.",
        output_pdf_path=output_path,
        created_at=datetime.utcnow(),
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s.id


# ── POST /forms/fill ──────────────────────────────────────────────────────────

class TestFillForm:

    def test_fill_form_template_not_found(self, client):
        """Returns 404 when template_id does not exist."""
        response = client.post("/forms/fill", json={
            "template_id": 999999,
            "input_text": "John Smith is a firefighter.",
        })
        assert response.status_code == 404

    def test_fill_form_missing_fields_returns_422(self, client):
        """Returns 422 when required fields are missing."""
        response = client.post("/forms/fill", json={
            "template_id": 1,
        })
        assert response.status_code == 422

    def test_fill_form_ollama_down_returns_503(self, client, db_session):
        """Returns 503 when Ollama is not reachable."""
        template_id = make_template(db_session)

        with patch("src.controller.Controller.fill_form",
                   side_effect=ConnectionError("Ollama not running")):
            response = client.post("/forms/fill", json={
                "template_id": template_id,
                "input_text": "John Smith is a firefighter.",
            })

        assert response.status_code == 503


# ── GET /forms/{submission_id} ────────────────────────────────────────────────

class TestGetSubmission:

    def test_get_submission_not_found(self, client):
        """Returns 404 for non-existent submission ID."""
        response = client.get("/forms/999999")
        assert response.status_code == 404

    def test_get_submission_invalid_id(self, client):
        """Returns 422 for non-integer submission ID."""
        response = client.get("/forms/not-an-id")
        assert response.status_code == 422


# ── GET /forms/download/{submission_id} ───────────────────────────────────────

class TestDownloadSubmission:

    def test_download_not_found_submission(self, client):
        """Returns 404 when submission does not exist."""
        response = client.get("/forms/download/999999")
        assert response.status_code == 404

    def test_download_file_missing_on_disk(self, client, db_session):
        """Returns 404 when submission exists but PDF missing on disk."""
        template_id = make_template(db_session)
        submission_id = make_submission(
            db_session, template_id, "/nonexistent/filled.pdf"
        )

        with patch("os.path.exists", return_value=False):
            response = client.get(f"/forms/download/{submission_id}")

        assert response.status_code == 404
