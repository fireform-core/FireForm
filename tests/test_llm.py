from unittest.mock import patch, MagicMock
import pytest
from app.services.llm import LLM


def test_llm_accepts_list_of_target_fields():
    """LLM should accept target_fields as a list of field names or dict."""
    llm = LLM(transcript_text="Station 4 responded to a structure fire on Elm Street.", target_fields=["station", "incident_type"])

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": "Station 4"}
    mock_resp.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_resp):
        result = llm.main_loop()

    data = result.get_data()
    assert data["station"] == "Station 4"
    assert data["incident_type"] == "Station 4"


def test_llm_add_response_to_json_handles_existing_key():
    """add_response_to_json should not crash with AttributeError when updating or appending values."""
    llm = LLM(transcript_text="Test", target_fields={})
    llm.add_response_to_json("unit", "Engine 1")
    assert llm.get_data()["unit"] == "Engine 1"

    # Adding a second response to the same field
    llm.add_response_to_json("unit", "Ladder 2")
    assert llm.get_data()["unit"] == ["Engine 1", "Ladder 2"]
