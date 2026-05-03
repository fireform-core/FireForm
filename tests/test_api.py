"""Comprehensive API tests for FireForm.

Covers every endpoint and the full upload → template → fill pipeline.
All heavy dependencies (LLM, commonforms, filesystem) are mocked via conftest.
"""

import pytest
from sqlmodel import select

from api.db.models import Template, FormSubmission


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
        resp = client.get("/templates")
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
        resp = client.post("/templates/create", json=payload)
        assert resp.status_code == 200

        data = resp.json()
        assert data["id"] is not None
        assert data["name"] == "Fire Report"
        assert data["fields"]["Location"] == "string"
        # Controller.create_template was called with the pdf_path
        mock_controller["template_ctrl"].create_template.assert_called_once_with(
            "src/inputs/fire_report.pdf"
        )

    def test_create_then_list(self, client, mock_controller):
        """Creating a template should make it appear in the list."""
        client.post("/templates/create", json={
            "name": "T1",
            "pdf_path": "a.pdf",
            "fields": {"f": "string"},
        })
        resp = client.get("/templates")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["name"] == "T1"

    def test_upload_pdf(self, client, pdf_upload, tmp_path, monkeypatch):
        """Upload a valid PDF file."""
        # Point the upload directory inside tmp_path (which is inside the project
        # for the path-safety check — we monkeypatch the check).
        monkeypatch.setattr(
            "api.routes.templates.PROJECT_ROOT",
            tmp_path,
        )
        resp = client.post(
            "/templates/upload",
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
        resp = client.post("/templates/upload", files=[bad_file])
        assert resp.status_code == 400
        assert "PDF" in resp.json()["detail"]

    def test_preview_missing_file(self, client):
        resp = client.get("/templates/preview", params={"path": "src/inputs/nonexistent.pdf"})
        assert resp.status_code == 404

    def test_directory_traversal_blocked(self, client):
        import io
        pdf = ("file", ("evil.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"))
        resp = client.post(
            "/templates/upload",
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
        resp = client.post("/templates/create", json={
            "name": "Employee Form",
            "pdf_path": "src/inputs/employee.pdf",
            "fields": {
                "Employee's name": "string",
                "Employee's email": "string",
            },
        })
        return resp.json()["id"]

    def test_fill_form_success(self, client, mock_controller):
        tpl_id = self._seed_template(client, mock_controller)

        resp = client.post("/forms/fill", json={
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
        resp = client.post("/forms/fill", json={
            "template_id": 9999,
            "input_text": "some text",
        })
        assert resp.status_code == 404

    def test_fill_form_validates_body(self, client):
        """Missing required fields → 422."""
        resp = client.post("/forms/fill", json={})
        assert resp.status_code == 422


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
        monkeypatch.setattr("api.routes.templates.PROJECT_ROOT", tmp_path)
        upload_resp = client.post(
            "/templates/upload",
            files=[pdf_upload],
            data={"directory": str(tmp_path)},
        )
        assert upload_resp.status_code == 200
        uploaded_path = upload_resp.json()["pdf_path"]
        assert uploaded_path.endswith(".pdf")

        # -- Step 2: Create a template from the uploaded PDF --
        create_resp = client.post("/templates/create", json={
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
        list_resp = client.get("/templates")
        assert list_resp.status_code == 200
        templates = list_resp.json()
        assert any(t["id"] == template_id for t in templates)

        # -- Step 4: Fill the form --
        fill_resp = client.post("/forms/fill", json={
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
