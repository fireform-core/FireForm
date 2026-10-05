"""Tests for async job submission and status endpoints."""

from unittest.mock import patch, MagicMock
from uuid import uuid4

from app.api.schemas.enums import InputStatus, InputType
from app.core.config import API_PREFIX
from app.models import Input


class TestJobEndpoints:

    def _seed_template(self, client):
        resp = client.post(f"{API_PREFIX}/templates/create", json={
            "name": "Test Template",
            "pdf_path": "test.pdf",
            "fields": {"name": "string"},
        })
        return resp.json()["id"]

    def _seed_input(self, db, status=InputStatus.ready, transcript="John Doe firefighter"):
        record = Input(input_type=InputType.text, status=status, transcript=transcript)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record.input_id

    @patch("app.api.routes.jobs.fill_form_task")
    def test_submit_async_single(self, mock_task, client, db):
        mock_result = MagicMock()
        mock_result.id = "celery-task-id-1"
        mock_task.delay.return_value = mock_result

        tpl_id = self._seed_template(client)
        input_id = self._seed_input(db)
        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [tpl_id],
            "input_id": str(input_id),
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["jobs"]) == 1
        assert data["jobs"][0]["status"] == "queued"
        assert "job_id" in data["jobs"][0]
        assert data["jobs"][0]["poll_url"].startswith(f"{API_PREFIX}/jobs/")
        mock_task.delay.assert_called_once_with(tpl_id, "John Doe firefighter", str(input_id), None)

    @patch("app.api.routes.jobs.fill_form_task")
    def test_submit_async_batch(self, mock_task, client, db):
        mock_task.delay.side_effect = [
            MagicMock(id="task-1"),
            MagicMock(id="task-2"),
        ]

        t1 = self._seed_template(client)
        t2 = self._seed_template(client)
        input_id = self._seed_input(db, transcript="batch input")
        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [t1, t2],
            "input_id": str(input_id),
        })
        assert resp.status_code == 200
        jobs = resp.json()["jobs"]
        assert len(jobs) == 2
        assert jobs[0]["job_id"] != jobs[1]["job_id"]
        assert mock_task.delay.call_count == 2

    @patch("app.api.routes.jobs.fill_form_task")
    def test_submit_async_missing_template(self, mock_task, client, db):
        input_id = self._seed_input(db, transcript="some text")
        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [9999],
            "input_id": str(input_id),
        })
        assert resp.status_code == 404
        mock_task.delay.assert_not_called()

    @patch("app.api.routes.jobs.fill_form_task")
    def test_submit_async_missing_input(self, mock_task, client):
        tpl_id = self._seed_template(client)
        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [tpl_id],
            "input_id": str(uuid4()),
        })
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "INPUT_NOT_FOUND"
        mock_task.delay.assert_not_called()

    @patch("app.api.routes.jobs.fill_form_task")
    def test_submit_async_input_transcribing(self, mock_task, client, db):
        """A not-yet-ready input is rejected up front — no job should be queued."""
        tpl_id = self._seed_template(client)
        input_id = self._seed_input(db, status=InputStatus.transcribing, transcript=None)

        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [tpl_id],
            "input_id": str(input_id),
        })
        assert resp.status_code == 409
        body = resp.json()
        assert body["error_code"] == "INPUT_NOT_READY"
        assert body["detail"]["status"] == "transcribing"
        mock_task.delay.assert_not_called()

    @patch("app.api.routes.jobs.fill_form_task")
    def test_submit_async_input_failed(self, mock_task, client, db):
        tpl_id = self._seed_template(client)
        input_id = self._seed_input(db, status=InputStatus.failed, transcript=None)

        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [tpl_id],
            "input_id": str(input_id),
        })
        assert resp.status_code == 409
        body = resp.json()
        assert body["error_code"] == "INPUT_NOT_READY"
        assert body["detail"]["status"] == "failed"
        mock_task.delay.assert_not_called()

    @patch("app.api.routes.jobs.fill_form_task")
    def test_get_job_status(self, mock_task, client, db):
        mock_task.delay.return_value = MagicMock(id="celery-abc")

        tpl_id = self._seed_template(client)
        input_id = self._seed_input(db, transcript="test input")
        submit_resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [tpl_id],
            "input_id": str(input_id),
        })
        job_id = submit_resp.json()["jobs"][0]["job_id"]

        resp = client.get(f"{API_PREFIX}/jobs/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["job_type"] == "form_generation"
        assert data["status"] == "queued"
        assert data["progress_percent"] == 0

    def test_get_job_not_found(self, client):
        resp = client.get(f"{API_PREFIX}/jobs/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    @patch("app.api.routes.jobs.fill_form_task")
    def test_submit_with_model_override(self, mock_task, client, db):
        mock_task.delay.return_value = MagicMock(id="celery-xyz")

        tpl_id = self._seed_template(client)
        input_id = self._seed_input(db, transcript="test")
        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [tpl_id],
            "input_id": str(input_id),
            "model": "mistral:latest",
        })
        assert resp.status_code == 200
        mock_task.delay.assert_called_once_with(tpl_id, "test", str(input_id), "mistral:latest")

    def test_submit_empty_template_ids(self, client, db):
        input_id = self._seed_input(db, transcript="test")
        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [],
            "input_id": str(input_id),
        })
        assert resp.status_code == 422

    def test_submit_invalid_input_id(self, client):
        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [1],
            "input_id": "not-a-uuid",
        })
        assert resp.status_code == 422
