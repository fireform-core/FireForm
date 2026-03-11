"""
Tests for LLM confidence validation and human-in-the-loop review logic.

These tests verify that:
1. High-confidence fields are written into the PDF normally.
2. Low-confidence fields are separated into the needs_review bucket.
3. LLM non-JSON responses are safely caught and flagged for review.
4. The CONFIDENCE_THRESHOLD constant is applied correctly.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from src.llm import LLM


CONFIDENCE_THRESHOLD = LLM.CONFIDENCE_THRESHOLD  # 0.85


def make_llm(fields: dict) -> LLM:
    """Helper: Create an LLM instance with a dummy transcript and target fields."""
    return LLM(
        transcript_text="The employee is John Doe. His badge number is 12345.",
        target_fields=fields,
        json={},
    )


def mock_ollama_response(value, confidence):
    """Helper: Build a mock requests.Response for the Ollama API."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "response": json.dumps({"value": value, "confidence": confidence})
    }
    return mock_resp


class TestAddResponseToJson:
    """Unit tests for LLM.add_response_to_json()"""

    def test_high_confidence_field_goes_into_confirmed(self):
        """A field with confidence >= threshold must end up in _json (confirmed)."""
        llm = make_llm({"employee_name": None})
        raw = json.dumps({"value": "John Doe", "confidence": 0.95})
        llm.add_response_to_json("employee_name", raw)

        assert llm.get_data()["employee_name"] == "John Doe"
        assert "employee_name" not in llm.get_needs_review()

    def test_low_confidence_field_goes_into_needs_review(self):
        """A field with confidence < threshold must end up in needs_review, not _json."""
        llm = make_llm({"badge_number": None})
        raw = json.dumps({"value": "99999", "confidence": 0.50})
        llm.add_response_to_json("badge_number", raw)

        assert "badge_number" not in llm.get_data()
        review = llm.get_needs_review()
        assert "badge_number" in review
        assert review["badge_number"]["suggested_value"] == "99999"
        assert review["badge_number"]["confidence"] == pytest.approx(0.50)

    def test_null_value_low_confidence_is_flagged(self):
        """A field where LLM says it couldn't find the value should be flagged."""
        llm = make_llm({"incident_code": None})
        raw = json.dumps({"value": None, "confidence": 0.0})
        llm.add_response_to_json("incident_code", raw)

        assert "incident_code" not in llm.get_data()
        assert "incident_code" in llm.get_needs_review()

    def test_non_json_response_is_safely_caught_and_flagged(self):
        """If the LLM returns garbage (not JSON), it must be caught and flagged — not crash."""
        llm = make_llm({"address": None})
        llm.add_response_to_json("address", "Sorry, I don't know the address.")

        assert "address" not in llm.get_data()
        assert "address" in llm.get_needs_review()

    def test_exactly_at_threshold_is_confirmed(self):
        """A field with confidence exactly equal to the threshold is confirmed (not flagged)."""
        llm = make_llm({"date": None})
        raw = json.dumps({"value": "01/02/2005", "confidence": CONFIDENCE_THRESHOLD})
        llm.add_response_to_json("date", raw)

        assert llm.get_data()["date"] == "01/02/2005"
        assert "date" not in llm.get_needs_review()


class TestMainLoop:
    """Integration tests for LLM.main_loop() with a mocked Ollama API."""

    @patch("src.llm.requests.post")
    def test_main_loop_separates_confirmed_and_flagged(self, mock_post):
        """main_loop must correctly separate high/low confidence fields from a real loop."""
        fields = {"employee_name": None, "badge_number": None}
        llm = make_llm(fields)

        # employee_name returns high confidence; badge_number returns low
        mock_post.side_effect = [
            mock_ollama_response("John Doe", 0.97),
            mock_ollama_response("???", 0.40),
        ]

        llm.main_loop()

        assert llm.get_data().get("employee_name") == "John Doe"
        assert "employee_name" not in llm.get_needs_review()

        assert "badge_number" not in llm.get_data()
        assert "badge_number" in llm.get_needs_review()
        assert llm.get_needs_review()["badge_number"]["confidence"] == pytest.approx(0.40)
