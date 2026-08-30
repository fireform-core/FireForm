"""Tests for POST /api/v1/extract/{input_id} and GET /api/v1/extract/{extract_id}.

Endpoint tests only — dispatch is mocked (no broker) and the LLM provider's
health is patched. The real chunked worker lands in #630, so there is no task
unit here; the stub task is exercised indirectly by the POST dispatch
assertions.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from app.api.schemas.enums import ExtractionStatus, InputStatus, InputType, ReportStatus
from app.services.llm.models import ProviderHealth
from app.db.repositories import (
    create_extraction,
    create_incident,
    create_input,
    get_extraction,
    get_job_by_uuid,
)
from app.models import Extraction, Incident, Input

POST_URL = "/api/v1/extract"
GET_URL = "/api/v1/extract"

_CONTRACT = {
    "schema_version": "1.1.0",
    "schema_name": "fireform_incident_contract",
    "incident": {"name": "Bear Creek Wildfire"},
    "location": {"city": "Reno", "state": "NV"},
}


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _provider(up: bool) -> ProviderHealth:
    """The provider health the route checks before it accepts a run."""
    return ProviderHealth(
        provider="ollama",
        label="Ollama",
        model="qwen2.5:1.5b",
        external=False,
        status="healthy" if up else "unhealthy",
        probed=True,
        detail=None if up else "connection refused",
    )


def _ready_input(db, status=InputStatus.ready) -> Input:
    now = datetime.now(timezone.utc)
    record = Input(
        input_type=InputType.text,
        status=status,
        transcript="Structure fire at 42 Oak St, two engines on scene, one civilian injury.",
        character_count=70,
        word_count=13,
        created_at=now,
        updated_at=now,
    )
    return create_input(db, record)


def _completed_extraction_with_incident(db, input_id) -> tuple[Extraction, Incident]:
    now = datetime.now(timezone.utc)
    extraction = create_extraction(
        db,
        Extraction(
            input_id=input_id,
            status=ExtractionStatus.completed,
            started_at=now,
            completed_at=now,
            model_used="qwen2.5:1.5b",
            processing_time_seconds=42.0,
        ),
    )
    incident = create_incident(
        db,
        Incident(
            extract_id=extraction.extract_id,
            status=ReportStatus.draft,
            incident_contract=_CONTRACT,
        ),
    )
    return extraction, incident


# ---------------------------------------------------------------------------
# POST /api/v1/extract/{input_id}
# ---------------------------------------------------------------------------

class TestCreateExtraction:

    def _post(self, client, input_id, body=None, ollama_up=True, celery_id="celery-extract-001"):
        mock_result = MagicMock()
        mock_result.id = celery_id
        with patch("app.api.routes.extraction.llm.health", return_value=_provider(ollama_up)), \
             patch("app.services.extraction.service.extract_task") as mock_task:
            mock_task.delay.return_value = mock_result
            resp = client.post(f"{POST_URL}/{input_id}", json=body)
            return resp, mock_task

    def test_202_returns_required_fields(self, client, db):
        inp = _ready_input(db)
        resp, _ = self._post(client, inp.input_id)
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "processing"
        assert body["job_type"] == "extraction"
        assert body["input_id"] == str(inp.input_id)
        assert "extract_id" in body
        assert "job_id" in body
        assert body["poll_url"] == f"/api/v1/extract/{body['extract_id']}"
        assert body["estimated_seconds"] == 60

    def test_202_creates_processing_extraction_row(self, client, db):
        inp = _ready_input(db)
        resp, _ = self._post(client, inp.input_id)
        extraction = get_extraction(db, UUID(resp.json()["extract_id"]))
        assert extraction is not None
        assert extraction.status == ExtractionStatus.processing
        assert extraction.input_id == inp.input_id
        assert extraction.started_at is not None

    def test_202_creates_extraction_job_row(self, client, db):
        inp = _ready_input(db)
        resp, _ = self._post(client, inp.input_id)
        job = get_job_by_uuid(db, resp.json()["job_id"])
        assert job is not None
        assert job.job_type == "extraction"
        assert job.celery_task_id == "celery-extract-001"

    def test_202_dispatch_called_with_extract_id_and_job_id(self, client, db):
        inp = _ready_input(db)
        resp, mock_task = self._post(client, inp.input_id)
        body = resp.json()
        mock_task.delay.assert_called_once()
        args = mock_task.delay.call_args[0]
        assert args[0] == body["extract_id"]
        assert args[1] == body["job_id"]

    def test_202_model_override_stored_on_job(self, client, db):
        inp = _ready_input(db)
        resp, _ = self._post(client, inp.input_id, body={"model_override": "llama3:8b"})
        job = get_job_by_uuid(db, resp.json()["job_id"])
        assert job.model == "llama3:8b"

    def test_404_input_not_found(self, client, db):
        resp, _ = self._post(client, uuid4())
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "INPUT_NOT_FOUND"

    def test_409_input_not_ready(self, client, db):
        inp = _ready_input(db, status=InputStatus.transcribing)
        resp, _ = self._post(client, inp.input_id)
        assert resp.status_code == 409
        body = resp.json()
        assert body["error_code"] == "INPUT_NOT_READY"
        assert body["detail"]["current_status"] == "transcribing"

    def test_409_extraction_already_exists(self, client, db):
        inp = _ready_input(db)
        existing = create_extraction(db, Extraction(input_id=inp.input_id))
        # Pinned rather than left to the environment, so a developer running
        # with the rerun flag on still tests the shipped behaviour.
        with patch("app.api.routes.extraction.EXTRACTION_ALLOW_RERUN", False):
            resp, _ = self._post(client, inp.input_id)
        assert resp.status_code == 409
        body = resp.json()
        assert body["error_code"] == "EXTRACTION_EXISTS"
        assert body["detail"]["existing_extract_id"] == str(existing.extract_id)

    def test_202_rerun_allowed_when_flag_is_on(self, client, db):
        # Development escape hatch: the same narrative can be extracted again
        # instead of having to be re-uploaded. The earlier extraction stays.
        inp = _ready_input(db)
        existing = create_extraction(db, Extraction(input_id=inp.input_id))
        with patch("app.api.routes.extraction.EXTRACTION_ALLOW_RERUN", True):
            resp, _ = self._post(client, inp.input_id)
        assert resp.status_code == 202
        assert resp.json()["extract_id"] != str(existing.extract_id)
        assert get_extraction(db, existing.extract_id) is not None

    def test_503_ollama_unavailable(self, client, db):
        inp = _ready_input(db)
        resp, _ = self._post(client, inp.input_id, ollama_up=False)
        assert resp.status_code == 503
        assert resp.json()["error_code"] == "LLM_UNAVAILABLE"

    def test_422_non_json_body_does_not_500(self, client, db):
        # A wrong content-type puts the raw bytes body on the validation error;
        # the error handler must still render a 422 rather than blow up on
        # serializing bytes.
        inp = _ready_input(db)
        with patch("app.api.routes.extraction.llm.health", return_value=_provider(True)):
            resp = client.post(
                f"{POST_URL}/{inp.input_id}",
                content=b"{}",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# GET /api/v1/extract/{extract_id}
# ---------------------------------------------------------------------------

class TestGetExtraction:

    def test_200_processing_shape(self, client, db):
        inp = _ready_input(db)
        extraction = create_extraction(
            db,
            Extraction(
                input_id=inp.input_id,
                status=ExtractionStatus.processing,
                started_at=datetime.now(timezone.utc),
            ),
        )
        resp = client.get(f"{GET_URL}/{extraction.extract_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "processing"
        assert body["extract_id"] == str(extraction.extract_id)
        assert body["input_id"] == str(inp.input_id)
        assert body["retry_after_seconds"] == 5
        assert "incident_contract" not in body

    def test_200_completed_shape_embeds_contract(self, client, db):
        inp = _ready_input(db)
        extraction, incident = _completed_extraction_with_incident(db, inp.input_id)
        resp = client.get(f"{GET_URL}/{extraction.extract_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["incident_id"] == str(incident.incident_id)
        assert body["model_used"] == "qwen2.5:1.5b"
        assert body["processing_time_seconds"] == 42.0
        assert body["incident_contract"]["incident"]["name"] == "Bear Creek Wildfire"
        assert body["incident_contract"]["location"]["city"] == "Reno"

    def test_200_failed_shape(self, client, db):
        inp = _ready_input(db)
        extraction = create_extraction(
            db,
            Extraction(
                input_id=inp.input_id,
                status=ExtractionStatus.failed,
                started_at=datetime.now(timezone.utc),
                error_type="LLM_UNAVAILABLE",
                error_detail="Ollama connection refused",
            ),
        )
        resp = client.get(f"{GET_URL}/{extraction.extract_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["error_type"] == "LLM_UNAVAILABLE"
        assert body["error_detail"] == "Ollama connection refused"
        assert body["retry_after_seconds"] is None

    def test_404_extraction_not_found(self, client, db):
        resp = client.get(f"{GET_URL}/{uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "EXTRACT_NOT_FOUND"
