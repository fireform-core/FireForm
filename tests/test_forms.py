"""
Integration tests for the /forms/fill endpoint — including multilingual input.
"""

from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_template(client):
    """Helper: create a template and return its ID."""
    payload = {
        "name": "Test Form",
        "pdf_path": "src/inputs/test.pdf",
        "fields": {
            "Employee name": "",
            "Job title": "",
        },
    }
    with patch("src.file_manipulator.prepare_form"):
        res = client.post("/templates/create", json=payload)
    assert res.status_code == 200
    return res.json()["id"]


def _ollama_mock(field_responses: dict):
    """Return a side_effect for requests.post that responds per field name."""

    def _side_effect(*args, **kwargs):
        prompt = kwargs.get("json", {}).get("prompt", "")
        mock_resp = MagicMock()
        for field, value in field_responses.items():
            if field in prompt:
                mock_resp.json.return_value = {"response": value}
                return mock_resp
        mock_resp.json.return_value = {"response": "-1"}
        return mock_resp

    return _side_effect


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_submit_form_english(client):
    """A basic English-language form submission should succeed."""
    template_id = _create_template(client)

    form_payload = {
        "template_id": template_id,
        "input_text": "The employee name is John Doe. His job title is Engineer.",
    }

    with patch("src.translator._detect_language", return_value="en"):
        with patch(
            "src.llm.requests.post",
            side_effect=_ollama_mock(
                {"Employee name": "John Doe", "Job title": "Engineer"}
            ),
        ):
            with patch("src.file_manipulator.FileManipulator.fill_form", return_value="output.pdf"):
                with patch("os.path.exists", return_value=True):
                    res = client.post("/forms/fill", json=form_payload)

    assert res.status_code == 200
    data = res.json()
    assert data["detected_language"] == "en"


def test_submit_form_french_input_translates(client):
    """
    French-language input should be detected, translated to English,
    and the API response should include detected_language='fr'.
    """
    template_id = _create_template(client)

    french_input = "Le nom de l'employé est Jean Dupont. Son titre de poste est Ingénieur."
    english_translation = "The employee's name is Jean Dupont. His job title is Engineer."

    form_payload = {
        "template_id": template_id,
        "input_text": french_input,
    }

    mock_translator_instance = MagicMock()
    mock_translator_instance.translate.return_value = english_translation
    mock_translator_cls = MagicMock(return_value=mock_translator_instance)

    with patch("src.translator._detect_language", return_value="fr"):
        with patch("deep_translator.GoogleTranslator", mock_translator_cls):
            with patch(
                "src.llm.requests.post",
                side_effect=_ollama_mock(
                    {"Employee name": "Jean Dupont", "Job title": "Engineer"}
                ),
            ):
                with patch("src.file_manipulator.FileManipulator.fill_form", return_value="output.pdf"):
                    with patch("os.path.exists", return_value=True):
                        res = client.post("/forms/fill", json=form_payload)

    assert res.status_code == 200
    data = res.json()
    assert data["detected_language"] == "fr"


def test_submit_form_arabic_input_translates(client):
    """
    Arabic-language input should be detected, translated, and the API
    response should reflect detected_language='ar'.
    """
    template_id = _create_template(client)

    arabic_input = "اسم الموظف هو محمد علي. مسمى وظيفته مهندس."
    english_translation = "The employee's name is Mohammed Ali. His job title is Engineer."

    form_payload = {
        "template_id": template_id,
        "input_text": arabic_input,
    }

    mock_translator_instance = MagicMock()
    mock_translator_instance.translate.return_value = english_translation
    mock_translator_cls = MagicMock(return_value=mock_translator_instance)

    with patch("src.translator._detect_language", return_value="ar"):
        with patch("deep_translator.GoogleTranslator", mock_translator_cls):
            with patch(
                "src.llm.requests.post",
                side_effect=_ollama_mock(
                    {"Employee name": "Mohammed Ali", "Job title": "Engineer"}
                ),
            ):
                with patch("src.file_manipulator.FileManipulator.fill_form", return_value="output.pdf"):
                    with patch("os.path.exists", return_value=True):
                        res = client.post("/forms/fill", json=form_payload)

    assert res.status_code == 200
    data = res.json()
    assert data["detected_language"] == "ar"
