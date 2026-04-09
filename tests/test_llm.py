import pytest
from unittest.mock import patch, MagicMock
from src.llm import LLM

# --- 1. Testing Type Checking ---
def test_initialization_type_errors():
    llm = LLM(transcript_text=123, target_fields=["Name"])

    with pytest.raises(TypeError):
        llm.type_check_all()

    llm2 = LLM(transcript_text="Test", target_fields="Name")
    with pytest.raises(TypeError):
        llm2.type_check_all()

# --- 2. Testing String Parsing Logic ---
def test_handle_plural_values():

    llm = LLM("dummy text", {"dummy_field": "string"}, json={})

    result = llm.handle_plural_values("value1; value2; value3")
    assert result == ["value1", "value2", "value3"]

def test_handle_plural_values_no_semicolon():
    llm = LLM("dummy text", {"dummy_field": "string"}, json={})

    with pytest.raises(ValueError):
        llm.handle_plural_values("single_value_no_semicolon")

# --- 3. Testing the Core Loop with a Mocked LLM ---
@patch('src.llm.requests.post')
def test_main_loop_creates_valid_json(mock_post):
    mock_response = MagicMock()
    mock_response.json.side_effect = [{'response': 'John Doe'}, {'response': '-1'}]
    mock_post.return_value = mock_response

    fields = {"Name": "string", "Address": "string"}

    llm = LLM("My name is John Doe.", fields, json={})

    llm.main_loop()
    result_data = llm.get_data()

    assert mock_post.call_count == 2
    assert result_data["Name"] == "John Doe"
    assert result_data.get("Address") is None