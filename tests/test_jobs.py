"""Tests for async job submission and status endpoints."""

from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch
from uuid import uuid4

import pytest
from sqlmodel import select

from app.api.schemas.enums import InputStatus, InputType, JobStatus
from app.core.config import API_PREFIX
from app.models import Input, Job
from app.services.form_filler.exceptions import ModelNotInstalledError
from app.tasks.fill import fill_form_task


class TestJobEndpoints:
    def _seed_template(
        self,
        client,
        name="T1",
        pdf_path="src/inputs/t.pdf",
        description="Template used for job tests",
    ):
        resp = client.post(
            f"{API_PREFIX}/templates/create",
            json={
                "name": name,
                "description": description,
                "pdf_path": pdf_path,
                "fields": {"name": "string"},
            },
        )
        assert resp.status_code == 200, resp.json()
        return resp.json()["id"]

    def _seed_input(
        self,
        db,
        status=InputStatus.ready,
        transcript="John Doe firefighter",
    ):
        record = Input(
            input_type=InputType.text,
            status=status,
            transcript=transcript,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record.input_id

    @patch("app.api.routes.jobs.fill_form_task")
    def test_submit_async_single(self, mock_task, client, db):
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
        mock_task.apply_async.assert_called_once_with(
            (tpl_id, "John Doe firefighter", str(input_id), None),
            task_id=data["jobs"][0]["job_id"],
        )

    @patch("app.api.routes.jobs.fill_form_task")
    def test_submit_async_batch(self, mock_task, client, db):
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
        assert mock_task.apply_async.call_count == 2

    @patch("app.api.routes.jobs.fill_form_task")
    def test_submit_async_missing_template(self, mock_task, client, db):
        input_id = self._seed_input(db, transcript="some text")
        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [9999],
            "input_id": str(input_id),
        })
        assert resp.status_code == 404
        mock_task.apply_async.assert_not_called()

    @patch("app.api.routes.jobs.fill_form_task")
    def test_submit_async_missing_input(self, mock_task, client):
        tpl_id = self._seed_template(client)
        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [tpl_id],
            "input_id": str(uuid4()),
        })
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "INPUT_NOT_FOUND"
        mock_task.apply_async.assert_not_called()

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
        mock_task.apply_async.assert_not_called()

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
        mock_task.apply_async.assert_not_called()

    @patch("app.api.routes.jobs.fill_form_task")
    def test_get_job_status(self, mock_task, client, db):
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
        tpl_id = self._seed_template(client)
        input_id = self._seed_input(db, transcript="test")
        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [tpl_id],
            "input_id": str(input_id),
            "model": "mistral:latest",
        })
        assert resp.status_code == 200
        mock_task.apply_async.assert_called_once_with(
            (tpl_id, "test", str(input_id), "mistral:latest"), task_id=ANY
        )

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

    @patch("app.api.routes.jobs.fill_form_task")
    def test_submit_async_queue_unavailable(self, mock_task, client, db):
        mock_task.apply_async.side_effect = ConnectionError("redis down")

        tpl_id = self._seed_template(client)
        input_id = self._seed_input(db)
        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [tpl_id],
            "input_id": str(input_id),
        })
        assert resp.status_code == 503
        assert resp.json()["error_code"] == "QUEUE_UNAVAILABLE"
        job = db.exec(select(Job)).one()
        assert job.status == JobStatus.failed
        assert job.error["error_code"] == "QUEUE_UNAVAILABLE"

    def test_fill_task_preserves_model_not_installed_error_code(self):
        session = MagicMock()
        job = SimpleNamespace(status=JobStatus.queued, progress_percent=0, error=None)

        with (
            patch("app.tasks.fill.get_session", return_value=iter([session])),
            patch("app.tasks.fill.get_job_by_celery_id", side_effect=[job, job]),
            patch("app.tasks.fill.get_template", return_value=object()),
            patch(
                "app.tasks.fill.FormService.fill_and_persist",
                side_effect=ModelNotInstalledError("missing-model"),
            ),
        ):
            with pytest.raises(ModelNotInstalledError, match="missing-model"):
                fill_form_task.run(1, "text", str(uuid4()), "missing-model")

        assert job.error == {
            "error_code": "MODEL_NOT_INSTALLED",
            "message": "Model 'missing-model' is not installed in Ollama.",
        }
