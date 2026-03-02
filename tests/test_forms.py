from unittest.mock import patch


def test_submit_form(client):
    # Step 1: Create a template first
    with patch("api.routes.templates.Controller") as MockController:
        MockController.return_value.create_template.return_value = "src/inputs/file_template.pdf"

        template_payload = {
            "name": "Test Template",
            "pdf_path": "src/inputs/file.pdf",
            "fields": {
                "reporting_officer": "string",
                "incident_location": "string",
                "amount_of_victims": "string",
                "victim_name_s": "string",
                "assisting_officer": "string",
            },
        }
        template_res = client.post("/templates/create", json=template_payload)
        assert template_res.status_code == 200
        template_id = template_res.json()["id"]

    # Step 2: Fill form using that template
    with patch("api.routes.forms.Controller") as MockController:
        MockController.return_value.fill_form.return_value = "src/outputs/filled_test.pdf"

        form_payload = {
            "template_id": template_id,
            "input_text": (
                "Officer Voldemort here, at an incident reported at 456 Oak Street. "
                "Two victims, Mark Smith and Jane Doe. "
                "Handed off to Sheriff's Deputy Alvarez. End of transmission."
            ),
        }

        response = client.post("/forms/fill", json=form_payload)

        assert response.status_code == 200
        data = response.json()
        assert data["template_id"] == template_id
        assert data["output_pdf_path"] == "src/outputs/filled_test.pdf"
        assert data["input_text"] == form_payload["input_text"]
        assert "id" in data


def test_submit_form_invalid_template(client):
    with patch("api.routes.forms.Controller") as MockController:
        MockController.return_value.fill_form.return_value = "src/outputs/filled_test.pdf"

        form_payload = {
            "template_id": 99999,
            "input_text": "Some random incident text here.",
        }

        response = client.post("/forms/fill", json=form_payload)
        assert response.status_code == 404


def test_submit_form_missing_input_text(client):
    with patch("api.routes.forms.Controller") as MockController:
        MockController.return_value.fill_form.return_value = "src/outputs/filled_test.pdf"

        form_payload = {
            "template_id": 1,
        }

        response = client.post("/forms/fill", json=form_payload)
        assert response.status_code == 422
