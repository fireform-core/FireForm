"""Tests for DELETE /api/v1/templates/{id}, DELETE /api/v1/forms/{id},
POST /api/v1/forms/purge, and API-key access control.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import API_PREFIX
from app.models import FormSubmission, Template

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_template(client, name="T1", pdf_path="src/inputs/t.pdf"):
    resp = client.post(f"{API_PREFIX}/templates/create", json={
        "name": name,
        "pdf_path": pdf_path,
        "fields": {"name": "string"},
    })
    assert resp.status_code == 200, resp.json()
    return resp.json()["id"]


def _seed_submission(db, template_id, output_pdf_path="src/outputs/out.pdf"):
    sub = FormSubmission(
        template_id=template_id,
        input_text="John Doe, firefighter",
        output_pdf_path=output_pdf_path,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub.id


# ===========================================================================
# DELETE /api/v1/templates/{template_id}
# ===========================================================================

class TestDeleteTemplate:

    def test_delete_template_no_key_required_when_unconfigured(self, client):
        """No API key needed when FIREFORM_API_KEY is empty (default)."""
        tpl_id = _seed_template(client)
        resp = client.delete(f"{API_PREFIX}/templates/{tpl_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"

    def test_delete_template_removes_from_db(self, client, db):
        tpl_id = _seed_template(client)
        client.delete(f"{API_PREFIX}/templates/{tpl_id}")
        assert db.get(Template, tpl_id) is None

    def test_delete_template_not_found(self, client):
        resp = client.delete(f"{API_PREFIX}/templates/99999")
        assert resp.status_code == 404

    def test_delete_template_cascades_submissions(self, client, db):
        tpl_id = _seed_template(client)
        sub_id = _seed_submission(db, tpl_id)

        client.delete(f"{API_PREFIX}/templates/{tpl_id}")

        assert db.get(FormSubmission, sub_id) is None
        assert db.get(Template, tpl_id) is None

    def test_delete_template_deletes_pdf_file(self, client, tmp_path, monkeypatch):
        """Verify the template PDF file is removed from disk on delete."""
        monkeypatch.setattr("app.core.paths.PROJECT_ROOT", tmp_path)
        pdf_file = tmp_path / "myform.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        relative_path = "myform.pdf"
        tpl_id = _seed_template(client, pdf_path=relative_path)

        client.delete(f"{API_PREFIX}/templates/{tpl_id}")
        assert not pdf_file.exists()

    def test_delete_template_deletes_submission_output_pdfs(self, client, db, tmp_path, monkeypatch):
        """Output PDFs of related submissions should be wiped on template deletion."""
        monkeypatch.setattr("app.core.paths.PROJECT_ROOT", tmp_path)

        out_pdf = tmp_path / "filled.pdf"
        out_pdf.write_bytes(b"%PDF-1.4 filled")

        tpl_id = _seed_template(client, pdf_path="tpl.pdf")
        _seed_submission(db, tpl_id, output_pdf_path="filled.pdf")

        client.delete(f"{API_PREFIX}/templates/{tpl_id}")
        assert not out_pdf.exists()


# ===========================================================================
# DELETE /api/v1/forms/{submission_id}
# ===========================================================================

class TestDeleteSubmission:

    def test_delete_submission_no_key_when_unconfigured(self, client, db):
        tpl_id = _seed_template(client)
        sub_id = _seed_submission(db, tpl_id)
        resp = client.delete(f"{API_PREFIX}/forms/{sub_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_delete_submission_removes_from_db(self, client, db):
        tpl_id = _seed_template(client)
        sub_id = _seed_submission(db, tpl_id)
        client.delete(f"{API_PREFIX}/forms/{sub_id}")
        assert db.get(FormSubmission, sub_id) is None

    def test_delete_submission_not_found(self, client):
        resp = client.delete(f"{API_PREFIX}/forms/99999")
        assert resp.status_code == 404

    def test_delete_submission_removes_output_pdf(self, client, db, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.paths.PROJECT_ROOT", tmp_path)
        out_pdf = tmp_path / "filled_out.pdf"
        out_pdf.write_bytes(b"%PDF-1.4")

        tpl_id = _seed_template(client)
        sub_id = _seed_submission(db, tpl_id, output_pdf_path="filled_out.pdf")

        client.delete(f"{API_PREFIX}/forms/{sub_id}")
        assert not out_pdf.exists()


# ===========================================================================
# POST /api/v1/forms/purge
# ===========================================================================

class TestPurgeSubmissions:

    def _seed_old_submission(self, db, tpl_id, days_old=40):
        old_ts = datetime.now(timezone.utc) - timedelta(days=days_old)
        sub = FormSubmission(
            template_id=tpl_id,
            input_text="old data",
            output_pdf_path="src/outputs/old.pdf",
            created_at=old_ts,
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub.id

    def test_purge_removes_old_submissions(self, client, db):
        tpl_id = _seed_template(client)
        old_id = self._seed_old_submission(db, tpl_id, days_old=40)
        new_id = _seed_submission(db, tpl_id)  # recent

        resp = client.post(f"{API_PREFIX}/forms/purge?days=30")
        assert resp.status_code == 200
        assert resp.json()["purged_count"] == 1

        assert db.get(FormSubmission, old_id) is None
        assert db.get(FormSubmission, new_id) is not None

    def test_purge_nothing_to_remove(self, client, db):
        tpl_id = _seed_template(client)
        _seed_submission(db, tpl_id)  # recent
        resp = client.post(f"{API_PREFIX}/forms/purge?days=30")
        assert resp.status_code == 200
        assert resp.json()["purged_count"] == 0

    def test_purge_removes_output_pdf_file(self, client, db, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.paths.PROJECT_ROOT", tmp_path)
        out_pdf = tmp_path / "old_filled.pdf"
        out_pdf.write_bytes(b"%PDF-1.4")

        tpl_id = _seed_template(client)
        old_ts = datetime.now(timezone.utc) - timedelta(days=50)
        sub = FormSubmission(
            template_id=tpl_id,
            input_text="old",
            output_pdf_path="old_filled.pdf",
            created_at=old_ts,
        )
        db.add(sub)
        db.commit()

        resp = client.post(f"{API_PREFIX}/forms/purge?days=30")
        assert resp.status_code == 200
        assert not out_pdf.exists()


# ===========================================================================
# API-Key Access Control
# ===========================================================================

class TestApiKeyAccessControl:

    @pytest.fixture(autouse=True)
    def _set_api_key(self, monkeypatch):
        monkeypatch.setattr("app.api.deps.FIREFORM_API_KEY", "secret-test-key")

    def test_delete_template_requires_key_when_set(self, client):
        tpl_id = _seed_template(client)
        resp = client.delete(f"{API_PREFIX}/templates/{tpl_id}")
        assert resp.status_code == 401

    def test_delete_template_with_valid_x_api_key(self, client):
        tpl_id = _seed_template(client)
        resp = client.delete(
            f"{API_PREFIX}/templates/{tpl_id}",
            headers={"X-API-Key": "secret-test-key"},
        )
        assert resp.status_code == 200

    def test_delete_template_with_bearer_token(self, client):
        tpl_id = _seed_template(client)
        resp = client.delete(
            f"{API_PREFIX}/templates/{tpl_id}",
            headers={"Authorization": "Bearer secret-test-key"},
        )
        assert resp.status_code == 200

    def test_delete_template_wrong_key_rejected(self, client):
        tpl_id = _seed_template(client)
        resp = client.delete(
            f"{API_PREFIX}/templates/{tpl_id}",
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 401

    def test_delete_submission_requires_key_when_set(self, client, db):
        tpl_id = _seed_template(client)
        sub_id = _seed_submission(db, tpl_id)
        resp = client.delete(f"{API_PREFIX}/forms/{sub_id}")
        assert resp.status_code == 401

    def test_delete_submission_with_valid_key(self, client, db):
        tpl_id = _seed_template(client)
        sub_id = _seed_submission(db, tpl_id)
        resp = client.delete(
            f"{API_PREFIX}/forms/{sub_id}",
            headers={"X-API-Key": "secret-test-key"},
        )
        assert resp.status_code == 200

    def test_purge_requires_key_when_set(self, client):
        resp = client.post(f"{API_PREFIX}/forms/purge?days=30")
        assert resp.status_code == 401

    def test_purge_with_valid_key(self, client, db):
        resp = client.post(
            f"{API_PREFIX}/forms/purge?days=30",
            headers={"X-API-Key": "secret-test-key"},
        )
        assert resp.status_code == 200
