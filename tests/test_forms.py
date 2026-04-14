from api.db.models import Template
from src.controller import Controller


def test_submit_form(client, db_session, monkeypatch):
    template = Template(
        name="Template 1",
        fields={"Incident": "string"},
        pdf_path="src/inputs/file_template.pdf",
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)

    monkeypatch.setattr(
        Controller,
        "fill_form",
        lambda self, user_input, fields, pdf_form_path: "src/outputs/generated.pdf",
    )

    response = client.post(
        "/forms/fill",
        json={
            "template_id": template.id,
            "input_text": "Incident details",
        },
    )

    assert response.status_code == 200
    assert response.json()["template_id"] == template.id
    assert response.json()["output_pdf_path"] == "src/outputs/generated.pdf"
