def test_create_template(client):
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


def test_get_template_by_id(client):
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

    create_response = client.post("/templates/create", json=payload)
    template_id = create_response.json()["id"]

    response = client.get(f"/templates/{template_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == template_id
    assert data["name"] == payload["name"]
    assert data["fields"] == payload["fields"]


def test_get_template_by_id_not_found(client):
    response = client.get("/templates/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Template not found"
