def test_submit_form_complete_flow(client, monkeypatch):
    template_payload = {
        "name": "Template form complete",
        "pdf_path": "src/inputs/file.pdf",
        "fields": {
            "Incident location": {"required": True},
            "Incident date": {"required": True},
            "Reporter name": {"required": True},
        },
    }

    create_template_response = client.post("/templates/create", json=template_payload)
    assert create_template_response.status_code == 200
    template_id = create_template_response.json()["id"]

    def fake_fill_form(self, user_input, fields, pdf_form_path, retry_input_texts, max_retry_rounds):
        return {
            "output_pdf_path": "src/outputs/complete.pdf",
            "status": "completed",
            "required_completion_pct": 100,
            "completed_required_fields": [
                "Incident location",
                "Incident date",
                "Reporter name",
            ],
            "missing_required_fields": [],
            "attempts_used": 1,
            "retry_prompt": None,
        }

    monkeypatch.setattr("api.routes.forms.Controller.fill_form", fake_fill_form)

    form_payload = {
        "template_id": template_id,
        "input_text": "Incident happened near station 4 yesterday and was reported by Alex.",
        "retry_input_texts": [],
        "max_retry_rounds": 1,
    }
    response = client.post("/forms/fill", json=form_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["template_id"] == template_id
    assert data["status"] == "completed"
    assert data["required_completion_pct"] == 100
    assert data["missing_required_fields"] == []
    assert data["attempts_used"] == 1


def test_submit_form_incomplete_flow_returns_retry_prompt(client, monkeypatch):
    template_payload = {
        "name": "Template form incomplete",
        "pdf_path": "src/inputs/file.pdf",
        "fields": {
            "Incident location": {"required": True},
            "Incident date": {"required": True},
            "Reporter name": {"required": True},
        },
    }

    create_template_response = client.post("/templates/create", json=template_payload)
    assert create_template_response.status_code == 200
    template_id = create_template_response.json()["id"]

    def fake_fill_form(self, user_input, fields, pdf_form_path, retry_input_texts, max_retry_rounds):
        return {
            "output_pdf_path": None,
            "status": "incomplete",
            "required_completion_pct": 66,
            "completed_required_fields": ["Incident location", "Reporter name"],
            "missing_required_fields": ["Incident date"],
            "attempts_used": 2,
            "retry_prompt": "Some required information is still missing. Please answer these fields: Incident date.",
        }

    monkeypatch.setattr("api.routes.forms.Controller.fill_form", fake_fill_form)

    form_payload = {
        "template_id": template_id,
        "input_text": "Incident happened near station 4 and was reported by Alex.",
        "retry_input_texts": ["It happened on January 2nd."],
        "max_retry_rounds": 1,
    }
    response = client.post("/forms/fill", json=form_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["template_id"] == template_id
    assert data["status"] == "incomplete"
    assert data["required_completion_pct"] == 66
    assert data["missing_required_fields"] == ["Incident date"]
    assert data["attempts_used"] == 2
    assert data["retry_prompt"] is not None
