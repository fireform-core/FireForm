"""
Tests for /templates endpoints.
Closes #162, #160, #163
"""

import io
import pytest
from unittest.mock import patch, MagicMock
from api.db.models import Template
from datetime import datetime


# ── POST /templates/create ────────────────────────────────────────────────────

class TestCreateTemplate:

    def test_create_template_success(self, client):
        """Uploading a valid PDF returns 200 with template data."""
        pdf_bytes = (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f\n"
            b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF"
        )

        mock_fields = {
            "JobTitle": {"/T": "JobTitle", "/FT": "/Tx"},
            "Department": {"/T": "Department", "/FT": "/Tx"},
        }

        with patch("commonforms.prepare_form"), \
             patch("pypdf.PdfReader") as mock_reader, \
             patch("shutil.copyfileobj"), \
             patch("builtins.open", MagicMock()), \
             patch("os.path.exists", return_value=True), \
             patch("os.remove"):

            mock_reader.return_value.get_fields.return_value = mock_fields

            response = client.post(
                "/templates/create",
                files={"file": ("form.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
                data={"name": "Vaccine Form"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Vaccine Form"
        assert "id" in data
        assert "fields" in data

    def test_create_template_without_file_returns_422(self, client):
        """Missing file field returns 422 Unprocessable Entity."""
        response = client.post(
            "/templates/create",
            data={"name": "No File"},
        )
        assert response.status_code == 422

    def test_create_template_non_pdf_returns_400(self, client):
        """Uploading a non-PDF returns 400."""
        with patch("shutil.copyfileobj"), \
             patch("builtins.open", MagicMock()):
            response = client.post(
                "/templates/create",
                files={"file": ("data.csv", io.BytesIO(b"a,b,c"), "text/csv")},
                data={"name": "CSV attempt"},
            )
        assert response.status_code == 400


# ── GET /templates ────────────────────────────────────────────────────────────

class TestListTemplates:

    def test_list_templates_returns_200(self, client):
        """GET /templates returns 200."""
        response = client.get("/templates")
        assert response.status_code == 200

    def test_list_templates_returns_list(self, client):
        """Response is always a list."""
        response = client.get("/templates")
        assert isinstance(response.json(), list)

    def test_list_templates_empty_on_fresh_db(self, client):
        """Fresh DB returns empty list."""
        response = client.get("/templates")
        assert response.json() == []

    def test_list_templates_pagination_accepted(self, client):
        """Pagination params accepted without error."""
        response = client.get("/templates?limit=5&offset=0")
        assert response.status_code == 200


# ── GET /templates/{template_id} ──────────────────────────────────────────────

class TestGetTemplate:

    def test_get_template_not_found(self, client):
        """Returns 404 for non-existent ID."""
        response = client.get("/templates/999999")
        assert response.status_code == 404

    def test_get_template_invalid_id_type(self, client):
        """Returns 422 for non-integer ID."""
        response = client.get("/templates/not-an-id")
        assert response.status_code == 422

    def test_get_template_by_id(self, client, db_session):
        """Returns correct template for valid ID."""
        t = Template(
            name="Cal Fire Form",
            fields={"officer_name": "Officer Name"},
            pdf_path="/tmp/cal_fire.pdf",
            created_at=datetime.utcnow(),
        )
        db_session.add(t)
        db_session.commit()
        db_session.refresh(t)

        response = client.get(f"/templates/{t.id}")
        assert response.status_code == 200
        assert response.json()["name"] == "Cal Fire Form"
