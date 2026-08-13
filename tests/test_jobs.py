"""Tests for async job submission and status endpoints."""

from unittest.mock import MagicMock, patch

from app.core.config import API_PREFIX


class TestJobEndpoints:

    def _seed_template(self, client):
        resp = client.post(f"{API_PREFIX}/templates/create", json={
            "name": "Test Template",
            "pdf_path": "test.pdf",
            "fields": {"name": "string"},
        })
        return resp.json()["id"]

    @patch("app.api.routes.jobs.fill_form_task")
    def test_submit_async_single(self, mock_task, client):
        mock_result = MagicMock()
        mock_result.id = "celery-task-id-1"
        mock_task.delay.return_value = mock_result

        tpl_id = self._seed_template(client)
        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [tpl_id],
            "input_text": "John Doe firefighter",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["jobs"]) == 1
        assert data["jobs"][0]["status"] == "queued"
        assert "job_id" in data["jobs"][0]
        assert data["jobs"][0]["poll_url"].startswith(f"{API_PREFIX}/jobs/")
        mock_task.delay.assert_called_once_with(tpl_id, "John Doe firefighter", None)

    @patch("app.api.routes.jobs.fill_form_task")
    def test_submit_async_batch(self, mock_task, client):
        mock_task.delay.side_effect = [
            MagicMock(id="task-1"),
            MagicMock(id="task-2"),
        ]

        t1 = self._seed_template(client)
        t2 = self._seed_template(client)
        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [t1, t2],
            "input_text": "batch input",
        })
        assert resp.status_code == 200
        jobs = resp.json()["jobs"]
        assert len(jobs) == 2
        assert jobs[0]["job_id"] != jobs[1]["job_id"]
        assert mock_task.delay.call_count == 2

    @patch("app.api.routes.jobs.fill_form_task")
    def test_submit_async_missing_template(self, mock_task, client):
        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [9999],
            "input_text": "some text",
        })
        assert resp.status_code == 404
        mock_task.delay.assert_not_called()

    @patch("app.api.routes.jobs.fill_form_task")
    def test_get_job_status(self, mock_task, client):
        mock_task.delay.return_value = MagicMock(id="celery-abc")

        tpl_id = self._seed_template(client)
        submit_resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [tpl_id],
            "input_text": "test input",
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
    def test_submit_with_model_override(self, mock_task, client):
        mock_task.delay.return_value = MagicMock(id="celery-xyz")

        tpl_id = self._seed_template(client)
        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [tpl_id],
            "input_text": "test",
            "model": "mistral:latest",
        })
        assert resp.status_code == 200
        mock_task.delay.assert_called_once_with(tpl_id, "test", "mistral:latest")

    def test_submit_empty_template_ids(self, client):
        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [],
            "input_text": "test",
        })
        assert resp.status_code == 422

    def test_submit_empty_input_text(self, client):
        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [1],
            "input_text": "",
        })
        assert resp.status_code == 422
