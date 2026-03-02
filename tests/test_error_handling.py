"""
Tests for error handling — covers AppError registration, validation errors,
404 responses, and generic exception handling.
Resolves: #101 (AppError Not Registered)
Also verifies fixes for: #83/#78 (duplicate query removed)
"""


def test_app_error_returns_structured_json(client):
    """AppError should return structured JSON, not generic 500."""
    response = client.post(
        "/forms/fill",
        json={"template_id": 9999, "input_text": "test"},
    )
    assert response.status_code == 404

    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NotFoundError"
    assert "9999" in body["error"]["message"]


def test_validation_error_missing_field(client):
    """Missing required fields should return 422 with details."""
    response = client.post("/forms/fill", json={})
    assert response.status_code == 422

    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "ValidationError"


def test_validation_error_wrong_type(client):
    """Wrong field types should return 422."""
    response = client.post(
        "/forms/fill",
        json={"template_id": "not_an_int", "input_text": 123},
    )
    assert response.status_code == 422

    body = response.json()
    assert body["success"] is False


def test_error_response_never_leaks_stacktrace(client):
    """Error responses must never contain Python tracebacks."""
    response = client.post(
        "/forms/fill",
        json={"template_id": 9999, "input_text": "test"},
    )

    body_str = response.text
    assert "Traceback" not in body_str
    assert 'File "' not in body_str


def test_create_template_success(client):
    """Successful template creation returns 200 with id."""
    payload = {
        "name": "Test Template",
        "pdf_path": "src/inputs/file.pdf",
        "fields": {"name": "string", "date": "string"},
    }

    response = client.post("/templates/create", json=payload)
    assert response.status_code == 200

    body = response.json()
    assert body["id"] is not None
    assert body["name"] == "Test Template"


def test_fill_form_success(client):
    """Full flow: create template then fill form."""
    tpl = client.post(
        "/templates/create",
        json={
            "name": "Flow Template",
            "pdf_path": "src/inputs/file.pdf",
            "fields": {"officer": "string", "location": "string"},
        },
    )
    template_id = tpl.json()["id"]

    response = client.post(
        "/forms/fill",
        json={
            "template_id": template_id,
            "input_text": "Officer Smith at 123 Main St",
        },
    )
    assert response.status_code == 200

    body = response.json()
    assert body["template_id"] == template_id
    assert body["output_pdf_path"] is not None


def test_create_template_missing_fields(client):
    """Template creation with missing fields returns 422."""
    response = client.post("/templates/create", json={"name": "Incomplete"})
    assert response.status_code == 422

    body = response.json()
    assert body["success"] is False
