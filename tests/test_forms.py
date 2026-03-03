from src.controller import Controller


def _template_payload(name: str):
    return {
        "name": name,
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


def test_get_form_submission_by_id(client, monkeypatch):
    monkeypatch.setattr(Controller, "fill_form", lambda self, user_input, fields, pdf_form_path: "filled_test.pdf")

    template_response = client.post("/templates/create", json=_template_payload("Form Template"))
    template_id = template_response.json()["id"]

    fill_response = client.post(
        "/forms/fill",
        json={"template_id": template_id, "input_text": "test transcript"},
    )
    submission_id = fill_response.json()["id"]

    response = client.get(f"/forms/{submission_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == submission_id
    assert data["template_id"] == template_id
    assert data["input_text"] == "test transcript"
    assert data["output_pdf_path"] == "filled_test.pdf"


def test_get_form_submission_by_id_not_found(client):
    response = client.get("/forms/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Form submission not found"
