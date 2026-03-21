import pytest


def test_create_template(client, monkeypatch):
    # Patch at the usage site: api.routes.templates imports Controller
    monkeypatch.setattr(
        "api.routes.templates.Controller.create_template",
        lambda _self, _pdf_path: "src/inputs/file_template.pdf",
        raising=True,
    )

    payload = {
        "name": "Template 1",
        "pdf_path": "src/inputs/file.pdf",
        "fields": {
            "Employee's name": "string",
            "Employee's job title": "string",
            "Employee's department supervisor": "string",
            "Employee's phone number": "string",
            "Employee's email": "string",
            "Signature": "string",
            "Date": "string",
        },
    }

    response = client.post("/templates/create", json=payload)

    assert response.status_code == 200
