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


def test_list_templates_empty(client):
    response = client.get("/templates")

    assert response.status_code == 200
    assert response.json() == []


def test_create_template(client):
    payload = _template_payload("Template 1")

    response = client.post("/templates/create", json=payload)

    assert response.status_code == 200


def test_list_templates_populated(client):
    client.post("/templates/create", json=_template_payload("Template A"))
    client.post("/templates/create", json=_template_payload("Template B"))

    response = client.get("/templates")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    names = [item["name"] for item in data]
    assert "Template A" in names
    assert "Template B" in names


def test_list_templates_pagination(client):
    response_before = client.get("/templates")
    existing = response_before.json()

    client.post("/templates/create", json=_template_payload("Template Paginated 1"))
    client.post("/templates/create", json=_template_payload("Template Paginated 2"))

    first_page = client.get(f"/templates?limit=1&offset={len(existing)}")
    second_page = client.get(f"/templates?limit=1&offset={len(existing) + 1}")

    assert first_page.status_code == 200
    assert second_page.status_code == 200

    first_data = first_page.json()
    second_data = second_page.json()

    assert len(first_data) == 1
    assert len(second_data) == 1
    assert first_data[0]["id"] != second_data[0]["id"]
