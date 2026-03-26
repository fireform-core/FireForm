"""Tests for standardized API error responses and global exception handlers."""

import json


def _assert_error_envelope(data: dict) -> None:
    assert "status_code" in data
    assert "code" in data
    assert "message" in data
    assert "details" in data


def test_validation_error_returns_standard_shape(client):
    response = client.post("/forms/fill", json={})
    assert response.status_code == 422
    data = response.json()
    _assert_error_envelope(data)
    assert data["code"] == "VALIDATION_ERROR"
    assert data["status_code"] == 422
    assert isinstance(data["details"], list)


def test_template_not_found_returns_code(client):
    response = client.post(
        "/forms/fill",
        json={"template_id": 999999, "input_text": "hello"},
    )
    assert response.status_code == 404
    data = response.json()
    _assert_error_envelope(data)
    assert data["code"] == "TEMPLATE_NOT_FOUND"
    assert data["message"] == "Template not found"
    assert data["details"] is None


def test_unknown_route_returns_not_found(client):
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404
    data = response.json()
    _assert_error_envelope(data)
    assert data["code"] == "NOT_FOUND"
    assert data["status_code"] == 404


def test_unhandled_exception_does_not_leak_internals(monkeypatch, client):
    def boom(*args, **kwargs):
        raise RuntimeError("secret-internal-token")

    monkeypatch.setattr("api.routes.forms.get_template", boom)

    response = client.post(
        "/forms/fill",
        json={"template_id": 1, "input_text": "hello"},
    )
    assert response.status_code == 500
    data = response.json()
    _assert_error_envelope(data)
    assert data["code"] == "INTERNAL_ERROR"
    assert "secret" not in json.dumps(data)


def test_pdf_not_found_returns_pdf_not_found(client):
    response = client.post(
        "/templates/create",
        json={
            "name": "n",
            "pdf_path": "/nonexistent/path/that/does/not/exist.pdf",
            "fields": {},
        },
    )
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "PDF_NOT_FOUND"
    assert data["details"] is not None
    assert "path" in data["details"]
