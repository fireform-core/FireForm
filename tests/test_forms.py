from src.controller import Controller


def test_submit_form(client, monkeypatch):
    template_payload = {
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

    def fake_create_template(self, pdf_path):
        assert pdf_path == template_payload["pdf_path"]
        return "src/inputs/file_template.pdf"

    monkeypatch.setattr(Controller, "create_template", fake_create_template)

    template_res = client.post("/templates/create", json=template_payload)
    assert template_res.status_code == 200
    template_id = template_res.json()["id"]

    form_payload = {
        "template_id": template_id,
        "input_text": "Hi. The employee's name is John Doe.",
    }

    def fake_fill_form(self, user_input, fields, pdf_form_path):
        assert user_input == form_payload["input_text"]
        assert fields == template_payload["fields"]
        assert pdf_form_path == "src/inputs/file_template.pdf"
        return "src/outputs/file_filled.pdf"

    monkeypatch.setattr(Controller, "fill_form", fake_fill_form)

    response = client.post("/forms/fill", json=form_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] is not None
    assert data["template_id"] == template_id
    assert data["input_text"] == form_payload["input_text"]
    assert data["output_pdf_path"] == "src/outputs/file_filled.pdf"


def test_submit_form_returns_404_for_missing_template(client):
    response = client.post(
        "/forms/fill",
        json={"template_id": 999999, "input_text": "Missing template test"},
    )

    assert response.status_code == 404
    assert response.json() == {"error": "Template not found"}
