"""Tests for GET /api/v1/health, /schema/incident, /schema/incident/versions.

External dependencies (the LLM provider, Whisper, disk, DB) are mocked at the
route-module boundary. The health check uses engine.connect() directly (not the
get_db dependency) so we mock system_mod.engine explicitly in every test.
"""

from unittest.mock import MagicMock

import pytest
import requests as requests_lib

import app.api.routes.system as system_mod
from app.services.llm.models import ModelInfo, ProviderHealth

# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _mock_engine_healthy():
    """Engine whose connect() succeeds — supports the 'with engine.connect()' pattern."""
    mock = MagicMock()
    # MagicMock already supports __enter__/__exit__ automatically
    return mock


def _mock_engine_down():
    mock = MagicMock()
    mock.connect.side_effect = Exception("Connection refused")
    return mock


def _mock_engine_execute_fails():
    """connect() succeeds (context manager enters) but execute() raises — simulates
    a connection acquired then lost, or a query timeout: the more realistic outage path.
    """
    mock = MagicMock()
    conn = MagicMock()
    conn.execute.side_effect = Exception("query failed: timeout")
    mock.connect.return_value.__enter__.return_value = conn
    return mock


def _mock_shutil(free_bytes: int = 120 * 1024 ** 3, raise_oserror: bool = False):
    """Return a shutil-shaped object whose disk_usage behaves as configured."""
    mock = MagicMock()
    if raise_oserror:
        mock.disk_usage.side_effect = OSError("disk error")
    else:
        usage = MagicMock()
        usage.free = free_bytes
        mock.disk_usage.return_value = usage
    return mock


def _fake_llm(
    monkeypatch,
    status="healthy",
    provider="ollama",
    model="llama3:8b",
    external=False,
    probed=True,
    response_time_ms=15,
    detail=None,
    models=("llama3:8b", "mistral:7b"),
):
    """Stand in for the LLM module the health route asks."""
    report = ProviderHealth(
        provider=provider,
        label=provider.title(),
        model=model,
        external=external,
        status=status,
        probed=probed,
        detail=detail,
        response_time_ms=response_time_ms,
    )
    monkeypatch.setattr(system_mod.llm, "health", lambda: report)
    monkeypatch.setattr(
        system_mod.llm,
        "list_models",
        lambda: [ModelInfo(name=name, default=name == model) for name in models],
    )
    return report


def _make_mock_response(json_data=None, status_code=200):
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_data or {}
    m.raise_for_status.return_value = None
    return m


# ---------------------------------------------------------------------------
# Canned Ollama / Whisper responses
# ---------------------------------------------------------------------------

_TAGS_RESPONSE = {
    "models": [
        {"name": "llama3:8b", "size": 5_000_000_000, "details": {"quantization_level": "Q4_K_M"}},
        {"name": "mistral:7b", "size": 4_000_000_000, "details": {"quantization_level": "Q4_0"}},
    ]
}
_VERSION_RESPONSE = {"version": "0.3.0"}
_PS_RESPONSE = {"models": [{"name": "llama3:8b"}]}
_PS_EMPTY = {"models": []}


def _fake_get_all_healthy(url, timeout=None):
    """All external services reachable and healthy."""
    if "/api/tags" in url:
        return _make_mock_response(_TAGS_RESPONSE)
    if "/api/version" in url:
        return _make_mock_response(_VERSION_RESPONSE)
    if "/api/ps" in url:
        return _make_mock_response(_PS_RESPONSE)
    if url.endswith("/docs"):
        return _make_mock_response()
    raise ValueError(f"Unexpected URL in test: {url}")


def _fake_get_ollama_down(url, timeout=None):
    """Ollama is unreachable; Whisper is healthy."""
    if "/api/tags" in url or "/api/version" in url or "/api/ps" in url:
        raise requests_lib.exceptions.ConnectionError("Ollama down")
    if url.endswith("/docs"):
        return _make_mock_response()
    raise ValueError(f"Unexpected URL in test: {url}")


def _fake_get_whisper_down(url, timeout=None):
    """Whisper is unreachable; Ollama is healthy."""
    if url.endswith("/docs"):
        raise requests_lib.exceptions.ConnectionError("Whisper down")
    if "/api/tags" in url:
        return _make_mock_response(_TAGS_RESPONSE)
    if "/api/version" in url:
        return _make_mock_response(_VERSION_RESPONSE)
    if "/api/ps" in url:
        return _make_mock_response(_PS_EMPTY)
    raise ValueError(f"Unexpected URL in test: {url}")


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:

    @pytest.fixture(autouse=True)
    def _healthy_llm(self, monkeypatch):
        """A working local provider, unless a test says otherwise."""
        _fake_llm(monkeypatch)

    def test_all_healthy(self, client, monkeypatch):
        monkeypatch.setattr(system_mod, "engine", _mock_engine_healthy())
        monkeypatch.setattr(system_mod, "shutil", _mock_shutil())
        monkeypatch.setattr("app.api.routes.system.requests.get", _fake_get_all_healthy)

        resp = client.get("/api/v1/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["version"] is not None
        assert body["uptime_seconds"] >= 0

        comps = body["components"]
        assert comps["database"]["status"] == "healthy"
        assert comps["llm"]["status"] == "healthy"
        assert comps["whisper"]["status"] == "healthy"
        assert comps["storage"]["status"] == "healthy"

    def test_llm_component_names_the_provider_and_model(self, client, monkeypatch):
        monkeypatch.setattr(system_mod, "engine", _mock_engine_healthy())
        monkeypatch.setattr(system_mod, "shutil", _mock_shutil())
        monkeypatch.setattr("app.api.routes.system.requests.get", _fake_get_all_healthy)

        component = client.get("/api/v1/health").json()["components"]["llm"]
        assert component["provider"] == "ollama"
        assert component["model"] == "llama3:8b"
        assert component["external"] is False
        assert component["probed"] is True

    def test_llm_down_returns_200_degraded(self, client, monkeypatch):
        monkeypatch.setattr(system_mod, "engine", _mock_engine_healthy())
        monkeypatch.setattr(system_mod, "shutil", _mock_shutil())
        monkeypatch.setattr("app.api.routes.system.requests.get", _fake_get_ollama_down)
        _fake_llm(monkeypatch, status="unhealthy", detail="connection refused")

        resp = client.get("/api/v1/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["components"]["llm"]["status"] == "unhealthy"
        assert body["components"]["database"]["status"] == "healthy"
        assert body["components"]["whisper"]["status"] == "healthy"

    def test_whisper_down_returns_200_degraded(self, client, monkeypatch):
        monkeypatch.setattr(system_mod, "engine", _mock_engine_healthy())
        monkeypatch.setattr(system_mod, "shutil", _mock_shutil())
        monkeypatch.setattr("app.api.routes.system.requests.get", _fake_get_whisper_down)

        resp = client.get("/api/v1/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["components"]["whisper"]["status"] == "unhealthy"
        assert body["components"]["llm"]["status"] == "healthy"

    def test_db_down_returns_503_unhealthy(self, client, monkeypatch):
        monkeypatch.setattr(system_mod, "engine", _mock_engine_down())
        monkeypatch.setattr(system_mod, "shutil", _mock_shutil())
        monkeypatch.setattr("app.api.routes.system.requests.get", _fake_get_all_healthy)

        resp = client.get("/api/v1/health")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "unhealthy"
        assert body["components"]["database"]["status"] == "unhealthy"
        assert "Connection refused" in body["components"]["database"]["detail"]

    def test_db_execute_fails_returns_503_unhealthy(self, client, monkeypatch):
        """connect() succeeds but execute() raises — the realistic outage path where
        a connection is acquired then the query times out or the server drops it.
        """
        monkeypatch.setattr(system_mod, "engine", _mock_engine_execute_fails())
        monkeypatch.setattr(system_mod, "shutil", _mock_shutil())
        monkeypatch.setattr("app.api.routes.system.requests.get", _fake_get_all_healthy)

        resp = client.get("/api/v1/health")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "unhealthy"
        assert body["components"]["database"]["status"] == "unhealthy"
        assert "query failed" in body["components"]["database"]["detail"]

    def test_slow_llm_returns_degraded(self, client, monkeypatch):
        """Patch _SLOW_MS to -1 so any measured elapsed time triggers degraded,
        without depending on wall-clock timing in CI.
        """
        monkeypatch.setattr(system_mod, "engine", _mock_engine_healthy())
        monkeypatch.setattr(system_mod, "shutil", _mock_shutil())
        monkeypatch.setattr("app.api.routes.system.requests.get", _fake_get_all_healthy)
        monkeypatch.setattr(system_mod, "_SLOW_MS", -1)

        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["components"]["llm"]["status"] == "degraded"

    def test_models_available_lists_what_the_provider_serves(self, client, monkeypatch):
        monkeypatch.setattr(system_mod, "engine", _mock_engine_healthy())
        monkeypatch.setattr(system_mod, "shutil", _mock_shutil())
        monkeypatch.setattr("app.api.routes.system.requests.get", _fake_get_all_healthy)

        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["components"]["llm"]["models_available"] == [
            "llama3:8b",
            "mistral:7b",
        ]

    def test_a_hosted_provider_is_flagged_and_not_listed(self, client, monkeypatch):
        """A hosted provider costs quota to ask, so health does not ask it."""
        monkeypatch.setattr(system_mod, "engine", _mock_engine_healthy())
        monkeypatch.setattr(system_mod, "shutil", _mock_shutil())
        monkeypatch.setattr("app.api.routes.system.requests.get", _fake_get_all_healthy)
        _fake_llm(
            monkeypatch,
            provider="gemini",
            model="gemini-2.0-flash",
            external=True,
            probed=False,
            response_time_ms=None,
            detail="hosted provider, not probed to avoid spending quota",
        )

        component = client.get("/api/v1/health").json()["components"]["llm"]
        assert component["external"] is True
        assert component["probed"] is False
        assert component.get("models_available") is None

    def test_storage_disk_free_present(self, client, monkeypatch):
        monkeypatch.setattr(system_mod, "engine", _mock_engine_healthy())
        monkeypatch.setattr(system_mod, "shutil", _mock_shutil(free_bytes=200 * 1024 ** 3))
        monkeypatch.setattr("app.api.routes.system.requests.get", _fake_get_all_healthy)

        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        storage = resp.json()["components"]["storage"]
        assert storage["status"] == "healthy"
        assert storage["disk_free_gb"] == pytest.approx(200.0, abs=0.1)

    def test_storage_unavailable_is_degraded(self, client, monkeypatch):
        monkeypatch.setattr(system_mod, "engine", _mock_engine_healthy())
        monkeypatch.setattr(system_mod, "shutil", _mock_shutil(raise_oserror=True))
        monkeypatch.setattr("app.api.routes.system.requests.get", _fake_get_all_healthy)

        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["components"]["storage"]["status"] == "unhealthy"

    def test_uptime_seconds_is_non_negative(self, client, monkeypatch):
        monkeypatch.setattr(system_mod, "engine", _mock_engine_healthy())
        monkeypatch.setattr(system_mod, "shutil", _mock_shutil())
        monkeypatch.setattr("app.api.routes.system.requests.get", _fake_get_all_healthy)

        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["uptime_seconds"] >= 0

    def test_existing_routes_not_displaced(self, client):
        """Sanity: adding v1_router must not break the existing /api/v1/templates endpoint."""
        resp = client.get("/api/v1/templates")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Schema stub endpoints
# ---------------------------------------------------------------------------

class TestSchemaStubEndpoints:

    def test_schema_incident_returns_501(self, client):
        resp = client.get("/api/v1/schema/incident")
        assert resp.status_code == 501
        body = resp.json()
        assert body["error_code"] == "NOT_IMPLEMENTED"
        assert "555" in body["message"]

    def test_schema_versions_returns_501(self, client):
        resp = client.get("/api/v1/schema/incident/versions")
        assert resp.status_code == 501
        body = resp.json()
        assert body["error_code"] == "NOT_IMPLEMENTED"
