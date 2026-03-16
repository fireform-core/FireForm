from src.controller import Controller


def test_create_template(client, monkeypatch):
    def fake_create_template(self, pdf_path):
        assert pdf_path == "src/inputs/file.pdf"
        return "src/inputs/file_template.pdf"

    monkeypatch.setattr(Controller, "create_template", fake_create_template)

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
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == payload["name"]
    assert data["fields"] == payload["fields"]
    assert data["pdf_path"] == "src/inputs/file_template.pdf"
