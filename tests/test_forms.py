from unittest.mock import patch


def test_submit_form(client):
    template_payload = {
        "name": "Test Template",
        "pdf_path": "sample.pdf",
        "fields": {
            "name": {},
            "job_title": {},
            "email": {}
        }
    }

    with patch("src.controller.Controller.create_template", return_value="template.pdf"), \
         patch("src.controller.Controller.fill_form", return_value="output.pdf"):

        template_res = client.post("/templates/create", json=template_payload)
        assert template_res.status_code == 200

        template_id = template_res.json()["id"]

        form_payload = {
            "template_id": template_id,
            "input_text": "John Doe is a managing director. Email is john@example.com."
        }

        response = client.post("/forms/fill", json=form_payload)

        assert response.status_code == 200

        data = response.json()
        assert data["template_id"] == template_id
        assert "output_pdf_path" in data


def test_submit_form_empty_input(client):
    template_payload = {
        "name": "Test Template",
        "pdf_path": "sample.pdf",
        "fields": {
            "name": {}
        }
    }

    with patch("src.controller.Controller.create_template", return_value="template.pdf"):

        template_res = client.post("/templates/create", json=template_payload)
        template_id = template_res.json()["id"]

        response = client.post("/forms/fill", json={
            "template_id": template_id,
            "input_text": ""
        })

        assert response.status_code == 400
        assert "Input text cannot be empty" in response.text


def test_submit_form_invalid_template(client):
    response = client.post("/forms/fill", json={
        "template_id": -1,
        "input_text": "Some valid text"
    })

    assert response.status_code == 400


def test_submit_form_long_input(client):
    long_text = "a" * 6000

    template_payload = {
        "name": "Test Template",
        "pdf_path": "sample.pdf",
        "fields": {
            "name": {}
        }
    }

    with patch("src.controller.Controller.create_template", return_value="template.pdf"):

        template_res = client.post("/templates/create", json=template_payload)
        template_id = template_res.json()["id"]

        response = client.post("/forms/fill", json={
            "template_id": template_id,
            "input_text": long_text
        })

        assert response.status_code == 400