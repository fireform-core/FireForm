def test_create_template(client):
    payload = {
        "name": "Template 1",
        "pdf_path": "src/inputs/file.pdf",
        "fields": {
            "Employee's name": "string",
            "Employee's job title": "string",
        },
    }

    response = client.post("/templates/create", json=payload)
    assert response.status_code == 200

    body = response.json()
    assert body["id"] is not None
    assert body["name"] == "Template 1"
    assert body["fields"] == payload["fields"]
