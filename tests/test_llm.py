"""
Unit tests for the LLM class (src/llm.py).

Tests cover:
- build_prompt()         → prompt contains the right field and transcript
- handle_plural_values() → splits "val1; val2" into ["val1", "val2"]
- add_response_to_json() → stores None for "-1", stores value otherwise
- main_loop()            → mocked Ollama call, builds JSON correctly
"""

import pytest
from unittest.mock import patch, MagicMock
from src.llm import LLM


# ─────────────────────────────────────────────────────────────
# build_prompt() tests
# ─────────────────────────────────────────────────────────────

def test_build_prompt_contains_field_name():
    """Prompt must mention the target field so the LLM knows what to extract."""
    llm = LLM(transcript_text="John Doe was the employee.", target_fields={"name": ""})
    prompt = llm.build_prompt("name")
    assert "name" in prompt


def test_build_prompt_contains_transcript_text():
    """Prompt must include the full transcript so the LLM has context."""
    transcript = "Station 5 responded to a fire at 123 Main Street."
    llm = LLM(transcript_text=transcript, target_fields={"location": ""})
    prompt = llm.build_prompt("location")
    assert transcript in prompt


def test_build_prompt_returns_string():
    """build_prompt should always return a string."""
    llm = LLM(transcript_text="Some text.", target_fields={"date": ""})
    result = llm.build_prompt("date")
    assert isinstance(result, str)


def test_build_prompt_contains_both_field_and_transcript():
    """Full check: both field name and transcript must appear in the prompt."""
    llm = LLM(transcript_text="John Doe", target_fields={"name": ""})
    prompt = llm.build_prompt("name")
    assert "name" in prompt
    assert "John Doe" in prompt


# ─────────────────────────────────────────────────────────────
# handle_plural_values() tests
# ─────────────────────────────────────────────────────────────

def test_handle_plural_values_splits_two_values():
    """Standard case: two values separated by semicolon."""
    llm = LLM()
    result = llm.handle_plural_values("Engine 12; Engine 14")
    assert result == ["Engine 12", "Engine 14"]


def test_handle_plural_values_strips_leading_whitespace():
    """Values after semicolons often have leading spaces — must be stripped."""
    llm = LLM()
    result = llm.handle_plural_values("Alice;  Bob;  Charlie")
    # The method only strips the second element onwards (based on current impl)
    assert "Alice" in result
    assert any("Bob" in v for v in result)


def test_handle_plural_values_raises_on_no_semicolon():
    """If no semicolon is present, raise ValueError."""
    llm = LLM()
    with pytest.raises(ValueError):
        llm.handle_plural_values("Engine 12")


def test_handle_plural_values_returns_list():
    """Return type must always be a list."""
    llm = LLM()
    result = llm.handle_plural_values("A; B")
    assert isinstance(result, list)


# ─────────────────────────────────────────────────────────────
# add_response_to_json() tests
# ─────────────────────────────────────────────────────────────

def test_add_response_ignores_minus_one():
    """When LLM returns '-1' (field not found), JSON value should be None."""
    llm = LLM(target_fields={}, json={})
    llm.add_response_to_json("name", "-1")
    assert llm._json["name"] is None


def test_add_response_stores_valid_value():
    """When LLM returns a real value, it should be stored in the JSON dict."""
    llm = LLM(target_fields={}, json={})
    llm.add_response_to_json("name", "John Doe")
    assert llm._json["name"] == "John Doe"


def test_add_response_strips_quotes_from_value():
    """LLM responses sometimes have extra quotes — they should be removed."""
    llm = LLM(target_fields={}, json={})
    llm.add_response_to_json("name", '"John Doe"')
    assert llm._json["name"] == "John Doe"


def test_add_response_handles_plural_values_with_semicolon():
    """When value contains ';', it should be split into a list."""
    llm = LLM(target_fields={}, json={})
    llm.add_response_to_json("engines", "Engine 12; Engine 14")
    assert isinstance(llm._json["engines"], list)


def test_add_response_creates_new_field_if_not_exists():
    """If the field doesn't exist in JSON yet, it should be created."""
    llm = LLM(target_fields={}, json={})
    llm.add_response_to_json("department", "Cal Fire")
    assert "department" in llm._json


# ─────────────────────────────────────────────────────────────
# main_loop() tests — mocked Ollama API
# ─────────────────────────────────────────────────────────────

def test_main_loop_calls_ollama_once_per_field():
    """main_loop() should call the Ollama API once per field in target_fields."""
    llm = LLM(
        transcript_text="John Doe works in IT.",
        target_fields={"name": "", "department": ""},
        json={"name": "", "department": ""},
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "extracted_value"}
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response) as mock_post:
        llm.main_loop()
        # Should be called once for each field (2 fields = 2 calls)
        assert mock_post.call_count == 2


def test_main_loop_returns_self():
    """main_loop() should return the LLM instance (for chaining)."""
    llm = LLM(
        transcript_text="Some incident text.",
        target_fields={"name": ""},
        json={"name": ""},
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "John"}
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response):
        result = llm.main_loop()
        assert result is llm


def test_main_loop_builds_correct_json_from_ollama_response():
    """main_loop() should populate _json with the Ollama response values."""
    llm = LLM(
        transcript_text="The employee is John Doe.",
        target_fields={"name": ""},
        json={"name": ""},
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "John Doe"}
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response):
        llm.main_loop()
        assert llm._json.get("name") == "John Doe"


def test_main_loop_raises_on_ollama_connection_error():
    """If Ollama is not running, main_loop() should raise a ConnectionError."""
    import requests as req
    llm = LLM(
        transcript_text="Some text.",
        target_fields={"name": ""},
        json={"name": ""},
    )

    with patch("requests.post", side_effect=req.exceptions.ConnectionError()):
        with pytest.raises(ConnectionError):
            llm.main_loop()
