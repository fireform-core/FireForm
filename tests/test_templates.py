from unittest.mock import patch


def test_create_template(client):
    with patch("api.routes.templates.Controller") as MockController:
        MockController.return_value.create_template.return_value = "src/inputs/file_template.pdf"

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
        assert data["name"] == "Template 1"
        assert data["pdf_path"] == "src/inputs/file_template.pdf"
        assert "id" in data


def test_create_template_missing_name(client):
    with patch("api.routes.templates.Controller") as MockController:
        MockController.return_value.create_template.return_value = "src/inputs/file_template.pdf"

        payload = {
            "pdf_path": "src/inputs/file.pdf",
            "fields": {"Employee's name": "string"},
        }

        response = client.post("/templates/create", json=payload)
        assert response.status_code == 422


def test_create_template_missing_fields(client):
    with patch("api.routes.templates.Controller") as MockController:
        MockController.return_value.create_template.return_value = "src/inputs/file_template.pdf"

        payload = {
            "name": "Bad Template",
            "pdf_path": "src/inputs/file.pdf",
        }

        response = client.post("/templates/create", json=payload)
        assert response.status_code == 422
