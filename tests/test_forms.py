from unittest.mock import patch, MagicMock

def test_interactive_feedback_loop(client):
    # 1) Create a template
    template_payload = {
        "name": "Test Form",
        "pdf_path": "src/inputs/test.pdf",
        "fields": {
            "Employee name": "",
            "Job title": ""
        }
    }
    
    with patch("api.routes.templates.prepare_form") as mock_prepare:
        template_res = client.post("/templates/create", json=template_payload)
        template_id = template_res.json()["id"]

    # 2) First Fill (Missing "Job title")
    form_payload = {
        "template_id": template_id,
        "input_text": "The employee name is John Doe."
    }

    def mock_ollama_call(*args, **kwargs):
        json_payload = kwargs.get("json", {})
        prompt = json_payload.get("prompt", "")
        
        mock_response = MagicMock()
        if "Employee name" in prompt:
            mock_response.json.return_value = {"response": "John Doe"}
        else:
            mock_response.json.return_value = {"response": "-1"}  # Missing
        return mock_response

    with patch("src.llm.requests.post", side_effect=mock_ollama_call):
        with patch("os.path.exists", return_value=True):
            response = client.post("/forms/fill", json=form_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "missing_data"
    assert "Job title" in data["missing_fields"]
    assert data["extracted_data"]["Employee name"] == "John Doe"
    submission_id = data["id"]

    # 3) Feedback (Providing "Job title")
    feedback_payload = {
        "input_text": "His job title is Engineer."
    }

    def mock_ollama_feedback(*args, **kwargs):
        json_payload = kwargs.get("json", {})
        prompt = json_payload.get("prompt", "")
        
        mock_response = MagicMock()
        if "Job title" in prompt:
            mock_response.json.return_value = {"response": "Engineer"}
        else:
            mock_response.json.return_value = {"response": "-1"}
        return mock_response

    with patch("src.llm.requests.post", side_effect=mock_ollama_feedback):
        with patch("src.filler.Filler.fill_form", return_value="output_path.pdf"):
            with patch("os.path.exists", return_value=True):
                feedback_res = client.post(f"/forms/{submission_id}/feedback", json=feedback_payload)

    assert feedback_res.status_code == 200
    feedback_data = feedback_res.json()
    assert feedback_data["status"] == "completed"
    assert len(feedback_data["missing_fields"]) == 0
    assert feedback_data["extracted_data"]["Job title"] == "Engineer"
    assert feedback_data["extracted_data"]["Employee name"] == "John Doe"
