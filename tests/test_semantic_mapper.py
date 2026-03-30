"""
Tests for the Dynamic AI Semantic Mapper — PR #2.

These tests cover:
- async_semantic_map: correctly maps Data Lake JSON to PDF fields via LLM
- async_semantic_map: handles synonym resolution (e.g. "Speaker" → "FullName")
- async_semantic_map: gracefully returns {} on LLM failure (no crash)
- async_semantic_map: handles empty master_json gracefully
- generate endpoint: uses Semantic Mapper output to fill PDF
- generate endpoint: falls back to exact matching if mapper returns empty dict
- generate endpoint: falls back gracefully if mapper raises exception

All Ollama/HTTP calls are mocked — no running Ollama instance required.
"""

import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, delete
from sqlalchemy.pool import StaticPool

from api.main import app
from api.deps import get_db
from api.db.models import Template, FormSubmission, IncidentMasterData
from api.db.repositories import create_incident, create_template
from src.llm import LLM

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


@pytest.fixture
def tmp_pdf(tmp_path):
    """Minimal valid PDF on disk for tests."""
    pdf_file = tmp_path / "test_form.pdf"
    pdf_file.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f\n"
        b"0000000009 00000 n\n"
        b"0000000058 00000 n\n"
        b"0000000115 00000 n\n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\n"
        b"startxref\n190\n%%EOF\n"
    )
    return str(pdf_file)


# ── Unit Tests: async_semantic_map ────────────────────────────────────

class TestSemanticMapperUnit:

    @pytest.mark.anyio
    async def test_maps_exact_keys_correctly(self):
        """Semantic Mapper returns correctly mapped JSON when LLM responds well."""
        master_json = {"OfficerName": "Jack Portman", "BadgeNumber": "EMP-001"}
        target_fields = ["OfficerName", "BadgeNumber"]

        # Simulate Ollama returning a perfect mapping
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": json.dumps({"OfficerName": "Jack Portman", "BadgeNumber": "EMP-001"})
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await LLM.async_semantic_map(master_json, target_fields)

        assert result["OfficerName"] == "Jack Portman"
        assert result["BadgeNumber"] == "EMP-001"

    @pytest.mark.anyio
    async def test_resolves_synonyms(self):
        """
        Key innovation: Semantic Mapper bridges synonym mismatches.
        Data Lake has 'Speaker', PDF wants 'FullName' — Mistral resolves it.
        """
        master_json = {"Speaker": "Jack Portman", "Identity": "EMP-001"}
        target_fields = ["FullName", "BadgeNumber"]

        # Simulate Ollama correctly bridging the synonym gap
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": json.dumps({"FullName": "Jack Portman", "BadgeNumber": "EMP-001"})
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await LLM.async_semantic_map(master_json, target_fields)

        # Mapper bridged the synonym gap — PDF gets 'FullName' not 'Speaker'
        assert result["FullName"] == "Jack Portman"
        assert result["BadgeNumber"] == "EMP-001"

    @pytest.mark.anyio
    async def test_returns_empty_dict_on_llm_failure(self):
        """Semantic Mapper returns {} gracefully if Ollama call raises exception."""
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("Ollama unreachable"))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await LLM.async_semantic_map(
                {"OfficerName": "Jack"}, ["FullName"]
            )

        assert result == {}

    @pytest.mark.anyio
    async def test_handles_empty_master_json(self):
        """Semantic Mapper handles empty Data Lake gracefully (new incident)."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": json.dumps({"FullName": None, "BadgeNumber": None})
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await LLM.async_semantic_map({}, ["FullName", "BadgeNumber"])

        assert isinstance(result, dict)

    @pytest.mark.anyio
    async def test_handles_json_parse_failure_gracefully(self):
        """Semantic Mapper returns {} if LLM response is not valid JSON."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": "Here is the mapping: invalid text, not json"
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await LLM.async_semantic_map(
                {"OfficerName": "Jack"}, ["FullName"]
            )

        assert result == {}


# ── Integration Tests: generate endpoint with Semantic Mapper ─────────

class TestSemanticMapperIntegration:

    def test_generate_uses_semantic_mapper_output(self, client, db_session, tmp_pdf):
        """
        Core test: generate endpoint uses Semantic Mapper to bridge
        mismatched Data Lake keys to PDF field names.
        """
        # Data Lake has 'Speaker', PDF wants 'FullName'
        incident = IncidentMasterData(
            incident_id="INC-SM-001",
            master_json=json.dumps({"Speaker": "Jack Portman", "Identity": "EMP-001"}),
            transcript_text="Jack Portman officer on scene.",
        )
        create_incident(db_session, incident)

        template = Template(
            name="Agency Form",
            fields={"FullName": "Full Name", "BadgeNo": "Badge Number"},
            pdf_path=tmp_pdf,
        )
        create_template(db_session, template)

        # Mock semantic mapper to return perfectly bridged keys
        mapped = {"FullName": "Jack Portman", "BadgeNo": "EMP-001"}
        with patch("api.routes.incidents.LLM") as mock_llm_cls:
            mock_llm_cls.async_semantic_map = AsyncMock(return_value=mapped)
            # Also mock filler so no actual PDF writing needed
            with patch("api.routes.incidents.Filler") as mock_filler_cls:
                mock_filler = MagicMock()
                mock_filler.fill_form_with_data.return_value = tmp_pdf
                mock_filler_cls.return_value = mock_filler

                response = client.post(f"/incidents/INC-SM-001/generate/{template.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["incident_id"] == "INC-SM-001"
        assert "download_url" in data
        assert data["message"] == "PDF physically generated via AI Semantic Mapping!"

    def test_generate_falls_back_when_mapper_returns_empty(self, client, db_session, tmp_pdf):
        """
        Resilience test: if Semantic Mapper returns {}, system falls back
        to exact string matching — PDF is always generated, never crashes.
        """
        incident = IncidentMasterData(
            incident_id="INC-SM-002",
            master_json=json.dumps({"FullName": "Alice Smith"}),
            transcript_text="Alice Smith officer.",
        )
        create_incident(db_session, incident)

        template = Template(
            name="Fallback Form",
            fields={"FullName": "Full Name"},
            pdf_path=tmp_pdf,
        )
        create_template(db_session, template)

        with patch("api.routes.incidents.LLM") as mock_llm_cls:
            # Mapper returns empty — should trigger fallback to exact matching
            mock_llm_cls.async_semantic_map = AsyncMock(return_value={})
            with patch("api.routes.incidents.Filler") as mock_filler_cls:
                mock_filler = MagicMock()
                mock_filler.fill_form_with_data.return_value = tmp_pdf
                mock_filler_cls.return_value = mock_filler

                response = client.post(f"/incidents/INC-SM-002/generate/{template.id}")

        assert response.status_code == 200

    def test_generate_falls_back_when_mapper_raises_exception(self, client, db_session, tmp_pdf):
        """
        Resilience test: if Semantic Mapper raises any exception,
        system falls back gracefully without a 500 error.
        """
        incident = IncidentMasterData(
            incident_id="INC-SM-003",
            master_json=json.dumps({"FullName": "Bob Jones"}),
            transcript_text="Bob Jones officer.",
        )
        create_incident(db_session, incident)

        template = Template(
            name="Crash Form",
            fields={"FullName": "Full Name"},
            pdf_path=tmp_pdf,
        )
        create_template(db_session, template)

        with patch("api.routes.incidents.LLM") as mock_llm_cls:
            mock_llm_cls.async_semantic_map = AsyncMock(
                side_effect=Exception("Ollama timeout")
            )
            with patch("api.routes.incidents.Filler") as mock_filler_cls:
                mock_filler = MagicMock()
                mock_filler.fill_form_with_data.return_value = tmp_pdf
                mock_filler_cls.return_value = mock_filler

                response = client.post(f"/incidents/INC-SM-003/generate/{template.id}")

        # Must not 500 — fallback kicks in
        assert response.status_code == 200

    def test_generate_still_returns_404_for_missing_incident(self, client):
        """Semantic Mapper does not affect 404 handling."""
        response = client.post("/incidents/INC-GHOST/generate/1")
        assert response.status_code == 404

    def test_generate_still_returns_404_for_missing_template(self, client, db_session):
        """Semantic Mapper does not affect 404 handling for missing templates."""
        incident = IncidentMasterData(
            incident_id="INC-SM-404",
            master_json=json.dumps({"OfficerName": "Test"}),
            transcript_text="Test.",
        )
        create_incident(db_session, incident)
        response = client.post("/incidents/INC-SM-404/generate/99999")
        assert response.status_code == 404
