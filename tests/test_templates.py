import sys
import types


def test_create_template(client, monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "commonforms",
        types.SimpleNamespace(prepare_form=lambda src, dest: dest),
    )

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
    assert response.json()["name"] == payload["name"]
    assert response.json()["pdf_path"].endswith("_template.pdf")
