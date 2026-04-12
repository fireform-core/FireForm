from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_create_template():
    payload = {
        "name": "integration test template",
        "fields": {
            "location": "",
            "time": "",
            "severity": "",
            "description": ""
        },
        "pdf_path": "/Users/arijitdeb/Documents/FireForm/src/inputs/file.pdf"
    }

    response = client.post("/templates/create", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "integration test template"


def test_fill_form():
    template_payload = {
        "name": "fill route test",
        "fields": {
            "location": "",
            "time": "",
            "severity": "",
            "description": ""
        },
        "pdf_path": "/Users/arijitdeb/Documents/FireForm/src/inputs/file.pdf"
    }

    template_response = client.post(
        "/templates/create",
        json=template_payload
    )

    template_id = template_response.json()["id"]

    fill_payload = {
        "template_id": template_id,
        "input_text": "Fire at Bangalore mall around 5 PM."
    }

    response = client.post("/forms/fill", json=fill_payload)

    assert response.status_code == 200