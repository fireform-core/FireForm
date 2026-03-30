"""
Tests for the Master Incident Data Lake — PR #1.

These tests cover:
- Creating a new incident record via POST /incidents/extract
- Retrieving an incident via GET /incidents/{id}
- Collaborative Consensus Merge (multi-officer append)
- 404 handling for unknown incidents / templates
- PDF generation from stored Data Lake record

The LLM (Ollama/Mistral) is mocked in all tests — no running
Ollama instance is required.
"""

import json
import pytest
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, delete
from sqlalchemy.pool import StaticPool

from api.main import app
from api.deps import get_db
from api.db.models import Template, FormSubmission, IncidentMasterData
from api.db.repositories import (
    create_incident,
    get_incident,
    update_incident_json,
)

# ── In-memory test database ────────────────────────────────────────────

TEST_DB_URL = "sqlite://"
engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def override_get_db():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def create_test_db():
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def clean_db():
    """Wipe all tables before each test — prevents leakage between tests."""
    with Session(engine) as session:
        session.exec(delete(FormSubmission))
        session.exec(delete(IncidentMasterData))
        session.exec(delete(Template))
        session.commit()
    yield


@pytest.fixture
def db_session():
    with Session(engine) as session:
        yield session


@pytest.fixture
def client():
    return TestClient(app)


# ── Mock LLM response ─────────────────────────────────────────────────

MOCK_EXTRACTED = {
    "OfficerName": "John Smith",
    "BadgeNumber": "EMP-001",
    "Location": "742 Evergreen Terrace",
    "IncidentType": "Structure Fire",
}


def make_mock_llm():
    """Returns a mock LLM object whose async_main_loop does nothing and get_data returns mock data."""
    mock = AsyncMock()
    mock.async_main_loop = AsyncMock(return_value=None)
    mock.get_data = lambda: MOCK_EXTRACTED
    return mock


# ── Unit Tests: Consensus Merge (no HTTP) ─────────────────────────────

class TestConsensusRepositoryLogic:

    def test_create_incident_persists(self, db_session):
        """Creating an incident stores it in the database."""
        incident = IncidentMasterData(
            incident_id="INC-UNIT-001",
            master_json=json.dumps({"OfficerName": "Alice"}),
            transcript_text="Officer Alice on scene.",
        )
        saved = create_incident(db_session, incident)
        assert saved.id is not None
        assert saved.incident_id == "INC-UNIT-001"

    def test_get_incident_retrieves_correct_record(self, db_session):
        """get_incident returns the correct record by incident_id."""
        incident = IncidentMasterData(
            incident_id="INC-UNIT-002",
            master_json=json.dumps({"OfficerName": "Bob"}),
            transcript_text="Officer Bob reporting.",
        )
        create_incident(db_session, incident)
        retrieved = get_incident(db_session, "INC-UNIT-002")
        assert retrieved is not None
        assert retrieved.incident_id == "INC-UNIT-002"

    def test_get_incident_returns_none_for_unknown(self, db_session):
        """get_incident returns None when incident does not exist."""
        result = get_incident(db_session, "INC-DOES-NOT-EXIST")
        assert result is None

    def test_consensus_merge_does_not_overwrite_with_null(self, db_session):
        """Smart merge: null/None values do NOT overwrite existing valid data."""
        incident = IncidentMasterData(
            incident_id="INC-MERGE-001",
            master_json=json.dumps({"OfficerName": "Alice", "BadgeNumber": "EMP-001"}),
            transcript_text="First report.",
        )
        create_incident(db_session, incident)

        # Second officer sends None for OfficerName — should NOT overwrite
        update_incident_json(
            db_session,
            "INC-MERGE-001",
            {"OfficerName": None, "Location": "742 Evergreen Terrace"},
            new_transcript="Second report.",
        )

        updated = get_incident(db_session, "INC-MERGE-001")
        result = json.loads(updated.master_json)
        assert result["OfficerName"] == "Alice"          # protected
        assert result["Location"] == "742 Evergreen Terrace"  # new field added

    def test_consensus_merge_appends_notes_field(self, db_session):
        """Smart merge: long-form text fields (Notes) append with [UPDATE] tag."""
        incident = IncidentMasterData(
            incident_id="INC-MERGE-002",
            master_json=json.dumps({"Notes": "Fire on ground floor."}),
            transcript_text="Initial note.",
        )
        create_incident(db_session, incident)

        update_incident_json(
            db_session,
            "INC-MERGE-002",
            {"Notes": "Victim evacuated safely."},
            new_transcript="Second note.",
        )

        updated = get_incident(db_session, "INC-MERGE-002")
        result = json.loads(updated.master_json)
        assert "Fire on ground floor." in result["Notes"]
        assert "[UPDATE]" in result["Notes"]
        assert "Victim evacuated safely." in result["Notes"]

    def test_consensus_merge_overwrites_short_fields_with_new_data(self, db_session):
        """Regular (non-notes) fields with real new values DO get updated."""
        incident = IncidentMasterData(
            incident_id="INC-MERGE-003",
            master_json=json.dumps({"Location": "Old Address"}),
            transcript_text="Initial.",
        )
        create_incident(db_session, incident)

        update_incident_json(
            db_session,
            "INC-MERGE-003",
            {"Location": "New Corrected Address"},
            new_transcript="Correction.",
        )

        updated = get_incident(db_session, "INC-MERGE-003")
        result = json.loads(updated.master_json)
        assert result["Location"] == "New Corrected Address"


# ── Integration Tests: API Endpoints ──────────────────────────────────

class TestDataLakeEndpoints:

    def test_extract_creates_new_incident(self, client):
        """POST /incidents/extract creates a new incident record."""
        with patch("api.routes.incidents.LLM", return_value=make_mock_llm()):
            response = client.post(
                "/incidents/extract",
                params={
                    "input_text": "Officer John Smith EMP-001 structure fire 742 Evergreen Terrace.",
                    "incident_id": "INC-E2E-001",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["incident_id"] == "INC-E2E-001"
        assert data["status"] == "created"

    def test_extract_merges_into_existing_incident(self, client):
        """POST /incidents/extract with same ID returns status 'merged'."""
        with patch("api.routes.incidents.LLM", return_value=make_mock_llm()):
            client.post(
                "/incidents/extract",
                params={"input_text": "First officer report.", "incident_id": "INC-E2E-002"},
            )
            response = client.post(
                "/incidents/extract",
                params={"input_text": "Second officer adding location.", "incident_id": "INC-E2E-002"},
            )
        assert response.status_code == 200
        assert response.json()["status"] == "merged"

    def test_get_incident_returns_stored_data(self, client, db_session):
        """GET /incidents/{id} returns the stored master JSON."""
        incident = IncidentMasterData(
            incident_id="INC-GET-001",
            master_json=json.dumps({"OfficerName": "Alice"}),
            transcript_text="Officer Alice.",
        )
        create_incident(db_session, incident)

        response = client.get("/incidents/INC-GET-001")
        assert response.status_code == 200
        data = response.json()
        assert data["incident_id"] == "INC-GET-001"
        assert data["master_json"]["OfficerName"] == "Alice"

    def test_get_nonexistent_incident_returns_404(self, client):
        """GET /incidents/{id} returns 404 for unknown ID."""
        response = client.get("/incidents/INC-GHOST-999")
        assert response.status_code == 404

    def test_generate_returns_404_for_missing_incident(self, client):
        """POST /incidents/{id}/generate/{template_id} returns 404 when incident missing."""
        response = client.post("/incidents/INC-MISSING/generate/1")
        assert response.status_code == 404

    def test_generate_returns_404_for_missing_template(self, client, db_session):
        """POST /incidents/{id}/generate/{template_id} returns 404 when template missing."""
        incident = IncidentMasterData(
            incident_id="INC-GEN-001",
            master_json=json.dumps({"OfficerName": "Alice"}),
            transcript_text="Officer Alice.",
        )
        create_incident(db_session, incident)
        response = client.post("/incidents/INC-GEN-001/generate/99999")
        assert response.status_code == 404

    def test_list_all_incidents(self, client, db_session):
        """GET /incidents returns a list of all stored incidents."""
        for i in range(3):
            create_incident(
                db_session,
                IncidentMasterData(
                    incident_id=f"INC-LIST-00{i}",
                    master_json=json.dumps({}),
                    transcript_text="test",
                ),
            )
        response = client.get("/incidents")
        assert response.status_code == 200
        assert len(response.json()) >= 3