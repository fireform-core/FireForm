def test_submit_form(client):
    from unittest.mock import MagicMock, patch

    # Step 1: create a template to get a valid template_id
    template_payload = {
        "name": "Test Form",
        "pdf_path": "src/inputs/file.pdf",
        "fields": {
            "name": "string",
            "date": "string",
        },
    }
    template_res = client.post("/templates/create", json=template_payload)
    assert template_res.status_code == 200
    template_id = template_res.json()["id"]

    # Step 2: submit a form fill request; mock Controller to avoid Ollama dependency
    fake_output_path = "src/outputs/file_20240101_120000_filled.pdf"
    form_payload = {
        "template_id": template_id,
        "input_text": "Employee name is John Doe. Date is 01/01/2024.",
    }

    with patch("api.routes.forms.Controller") as MockController:
        mock_ctrl = MagicMock()
        mock_ctrl.fill_form.return_value = fake_output_path
        MockController.return_value = mock_ctrl

        response = client.post("/forms/fill", json=form_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] is not None
    assert data["template_id"] == template_id
    assert data["input_text"] == form_payload["input_text"]
    assert data["output_pdf_path"] == fake_output_path
