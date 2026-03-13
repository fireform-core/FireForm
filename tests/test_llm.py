"""
Unit tests for src/llm.py — LLM class.

Closes: #186 (Unit tests for LLM class methods)
Covers: batch prompt, per-field prompt, add_response_to_json,
        handle_plural_values, type_check_all, main_loop (mocked)
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from src.llm import LLM


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def dict_fields():
    """Realistic dict fields: {internal_name: human_label}"""
    return {
        "NAME/SID":       "Employee Or Student Name",
        "JobTitle":       "Job Title",
        "Department":     "Department",
        "Phone Number":   "Phone Number",
        "email":          "Email",
    }

@pytest.fixture
def list_fields():
    """Legacy list fields: [internal_name, ...]"""
    return ["officer_name", "location", "incident_date"]

@pytest.fixture
def transcript():
    return (
        "Employee name is John Smith. Employee ID is EMP-2024-789. "
        "Job title is Firefighter Paramedic. Department is Emergency Medical Services. "
        "Phone number is 916-555-0147."
    )

@pytest.fixture
def llm_dict(dict_fields, transcript):
    return LLM(transcript_text=transcript, target_fields=dict_fields)

@pytest.fixture
def llm_list(list_fields, transcript):
    return LLM(transcript_text=transcript, target_fields=list_fields)


# ── type_check_all ────────────────────────────────────────────────────────────

class TestTypeCheckAll:

    def test_raises_on_non_string_transcript(self, dict_fields):
        llm = LLM(transcript_text=12345, target_fields=dict_fields)
        with pytest.raises(TypeError, match="Transcript must be text"):
            llm.type_check_all()

    def test_raises_on_none_transcript(self, dict_fields):
        llm = LLM(transcript_text=None, target_fields=dict_fields)
        with pytest.raises(TypeError):
            llm.type_check_all()

    def test_raises_on_invalid_fields_type(self, transcript):
        llm = LLM(transcript_text=transcript, target_fields="not_a_list_or_dict")
        with pytest.raises(TypeError, match="list or dict"):
            llm.type_check_all()

    def test_passes_with_dict_fields(self, llm_dict):
        # Should not raise
        llm_dict.type_check_all()

    def test_passes_with_list_fields(self, llm_list):
        # Should not raise
        llm_list.type_check_all()


# ── build_batch_prompt ────────────────────────────────────────────────────────

class TestBuildBatchPrompt:

    def test_contains_all_field_keys(self, llm_dict, dict_fields):
        prompt = llm_dict.build_batch_prompt()
        for key in dict_fields.keys():
            assert key in prompt, f"Field key '{key}' missing from batch prompt"

    def test_contains_human_labels(self, llm_dict, dict_fields):
        prompt = llm_dict.build_batch_prompt()
        for label in dict_fields.values():
            assert label in prompt, f"Label '{label}' missing from batch prompt"

    def test_contains_transcript(self, llm_dict, transcript):
        prompt = llm_dict.build_batch_prompt()
        assert transcript in prompt

    def test_contains_json_instruction(self, llm_dict):
        prompt = llm_dict.build_batch_prompt()
        assert "JSON" in prompt

    def test_list_fields_batch_prompt(self, llm_list, list_fields):
        prompt = llm_list.build_batch_prompt()
        for field in list_fields:
            assert field in prompt

    def test_labels_used_as_comments(self, llm_dict):
        """Human labels should appear after // in the prompt"""
        prompt = llm_dict.build_batch_prompt()
        assert "//" in prompt


# ── build_prompt (legacy per-field) ──────────────────────────────────────────

class TestBuildPrompt:

    def test_officer_field_gets_officer_guidance(self, llm_dict):
        prompt = llm_dict.build_prompt("officer_name")
        assert "OFFICER" in prompt.upper() or "EMPLOYEE" in prompt.upper()

    def test_location_field_gets_location_guidance(self, llm_dict):
        prompt = llm_dict.build_prompt("incident_location")
        assert "LOCATION" in prompt.upper() or "ADDRESS" in prompt.upper()

    def test_victim_field_gets_victim_guidance(self, llm_dict):
        prompt = llm_dict.build_prompt("victim_name")
        assert "VICTIM" in prompt.upper()

    def test_phone_field_gets_phone_guidance(self, llm_dict):
        prompt = llm_dict.build_prompt("Phone Number")
        assert "PHONE" in prompt.upper()

    def test_prompt_contains_transcript(self, llm_dict, transcript):
        prompt = llm_dict.build_prompt("some_field")
        assert transcript in prompt

    def test_generic_field_still_builds_prompt(self, llm_dict):
        prompt = llm_dict.build_prompt("textbox_0_0")
        assert len(prompt) > 50


# ── handle_plural_values ──────────────────────────────────────────────────────

class TestHandlePluralValues:

    def test_splits_on_semicolon(self, llm_dict):
        result = llm_dict.handle_plural_values("Mark Smith;Jane Doe")
        assert "Mark Smith" in result
        assert "Jane Doe" in result

    def test_strips_whitespace(self, llm_dict):
        result = llm_dict.handle_plural_values("Mark Smith; Jane Doe; Bob")
        assert all(v == v.strip() for v in result)

    def test_returns_list(self, llm_dict):
        result = llm_dict.handle_plural_values("A;B;C")
        assert isinstance(result, list)

    def test_raises_without_semicolon(self, llm_dict):
        with pytest.raises(ValueError, match="separator"):
            llm_dict.handle_plural_values("no semicolon here")

    def test_three_values(self, llm_dict):
        result = llm_dict.handle_plural_values("Alice;Bob;Charlie")
        assert len(result) == 3


# ── add_response_to_json ──────────────────────────────────────────────────────

class TestAddResponseToJson:

    def test_stores_value_under_field(self, llm_dict):
        llm_dict.add_response_to_json("NAME/SID", "John Smith")
        assert llm_dict._json["NAME/SID"] == "John Smith"

    def test_ignores_minus_one(self, llm_dict):
        llm_dict.add_response_to_json("email", "-1")
        assert llm_dict._json["email"] is None

    def test_strips_quotes(self, llm_dict):
        llm_dict.add_response_to_json("JobTitle", '"Firefighter"')
        assert llm_dict._json["JobTitle"] == "Firefighter"

    def test_strips_whitespace(self, llm_dict):
        llm_dict.add_response_to_json("Department", "  EMS  ")
        assert llm_dict._json["Department"] == "EMS"

    def test_plural_value_becomes_list(self, llm_dict):
        llm_dict.add_response_to_json("victims", "Mark Smith;Jane Doe")
        assert isinstance(llm_dict._json["victims"], list)

    def test_existing_field_becomes_list(self, llm_dict):
        """Adding to existing field should not overwrite silently."""
        llm_dict._json["NAME/SID"] = "John"
        llm_dict.add_response_to_json("NAME/SID", "Jane")
        assert isinstance(llm_dict._json["NAME/SID"], list)


# ── get_data ──────────────────────────────────────────────────────────────────

class TestGetData:

    def test_returns_dict(self, llm_dict):
        assert isinstance(llm_dict.get_data(), dict)

    def test_returns_same_reference_as_internal_json(self, llm_dict):
        llm_dict._json["test_key"] = "test_value"
        assert llm_dict.get_data()["test_key"] == "test_value"


# ── main_loop (mocked Ollama) ─────────────────────────────────────────────────

class TestMainLoop:

    def _mock_response(self, json_body: dict):
        """Build a mock requests.Response returning a valid Mistral JSON reply."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "response": json.dumps(json_body)
        }
        return mock_resp

    def test_batch_success_fills_all_fields(self, llm_dict, dict_fields):
        expected = {
            "NAME/SID":     "John Smith",
            "JobTitle":     "Firefighter Paramedic",
            "Department":   "Emergency Medical Services",
            "Phone Number": "916-555-0147",
            "email":        None,
        }
        with patch("requests.post", return_value=self._mock_response(expected)):
            llm_dict.main_loop()

        result = llm_dict.get_data()
        assert result["NAME/SID"] == "John Smith"
        assert result["JobTitle"] == "Firefighter Paramedic"
        assert result["Department"] == "Emergency Medical Services"
        assert result["Phone Number"] == "916-555-0147"

    def test_batch_makes_exactly_one_ollama_call(self, llm_dict, dict_fields):
        """Core performance requirement — O(1) not O(N)."""
        expected = {k: "value" for k in dict_fields.keys()}
        with patch("requests.post", return_value=self._mock_response(expected)) as mock_post:
            llm_dict.main_loop()

        assert mock_post.call_count == 1, (
            f"Expected 1 Ollama call, got {mock_post.call_count}. "
            "main_loop() must use batch extraction, not per-field."
        )

    def test_fallback_on_invalid_json(self, llm_dict, dict_fields):
        """If Mistral returns non-JSON, fallback per-field runs without crash."""
        bad_response = MagicMock()
        bad_response.raise_for_status = MagicMock()
        bad_response.json.return_value = {"response": "This is not JSON at all."}

        good_response = MagicMock()
        good_response.raise_for_status = MagicMock()
        good_response.json.return_value = {"response": "John Smith"}

        # First call returns bad JSON, rest return single values
        with patch("requests.post", side_effect=[bad_response] + [good_response] * len(dict_fields)):
            llm_dict.main_loop()  # should not raise

    def test_connection_error_raises_connection_error(self, llm_dict):
        import requests as req
        with patch("requests.post", side_effect=req.exceptions.ConnectionError):
            with pytest.raises(ConnectionError, match="Ollama"):
                llm_dict.main_loop()

    def test_null_values_stored_as_none(self, llm_dict, dict_fields):
        """Mistral returning null should be stored as None, not the string 'null'."""
        response_with_nulls = {k: None for k in dict_fields.keys()}
        with patch("requests.post", return_value=self._mock_response(response_with_nulls)):
            llm_dict.main_loop()

        result = llm_dict.get_data()
        for key in dict_fields.keys():
            assert result[key] is None, f"Expected None for '{key}', got {result[key]!r}"
