"""Unit tests for LLM Ollama retry logic, timeouts, and error handling."""

import json
from unittest.mock import patch

import pytest
import requests

from src.llm import LLM, OLLAMA_MAX_ATTEMPTS, OLLAMA_REQUEST_TIMEOUT


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Tenacity uses time.sleep between retries; disable for fast tests."""
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def ollama_host_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11434")


def _ok_json_response(body: dict) -> requests.Response:
    r = requests.Response()
    r.status_code = 200
    r.encoding = "utf-8"
    r._content = json.dumps(body).encode("utf-8")
    return r


def _http_error_response(status: int, reason: str = "") -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r.encoding = "utf-8"
    r.reason = reason or {400: "Bad Request", 404: "Not Found", 500: "Internal Server Error"}.get(
        status, "Error"
    )
    r._content = b'{"error":"fail"}'
    return r


@patch("src.llm.requests.post")
def test_retries_connection_error_then_success(mock_post):
    fails = [requests.exceptions.ConnectionError("refused")] * 2
    fails.append(_ok_json_response({"response": "extracted"}))
    mock_post.side_effect = fails

    llm = LLM(transcript_text="hello world", target_fields={"field_a": None})
    llm.main_loop()

    assert mock_post.call_count == 3
    assert llm.get_data()["field_a"] == "extracted"
    for call in mock_post.call_args_list:
        assert call.kwargs.get("timeout") == OLLAMA_REQUEST_TIMEOUT


@patch("src.llm.requests.post")
def test_timeout_exhausts_retries(mock_post):
    mock_post.side_effect = requests.exceptions.Timeout()

    llm = LLM(transcript_text="hello", target_fields={"f": None})

    with pytest.raises(RuntimeError, match="Ollama connection timed out"):
        llm.main_loop()

    assert mock_post.call_count == OLLAMA_MAX_ATTEMPTS


@patch("src.llm.requests.post")
def test_http_500_then_200(mock_post):
    mock_post.side_effect = [
        _http_error_response(500),
        _ok_json_response({"response": "ok"}),
    ]

    llm = LLM(transcript_text="hello", target_fields={"f": None})
    llm.main_loop()

    assert mock_post.call_count == 2
    assert llm.get_data()["f"] == "ok"


@pytest.mark.parametrize("status", [400, 404])
@patch("src.llm.requests.post")
def test_client_http_errors_do_not_retry(mock_post, status):
    mock_post.return_value = _http_error_response(status)

    llm = LLM(transcript_text="hello", target_fields={"f": None})

    with pytest.raises(RuntimeError, match="Ollama returned HTTP"):
        llm.main_loop()

    assert mock_post.call_count == 1


@patch("src.llm.requests.post")
def test_invalid_json_does_not_call_add_response_to_json(mock_post):
    r = requests.Response()
    r.status_code = 200
    r.encoding = "utf-8"
    r._content = b"not-json{{{"
    mock_post.return_value = r

    llm = LLM(transcript_text="hello", target_fields={"f": None})

    with patch.object(LLM, "add_response_to_json") as spy:
        with pytest.raises(RuntimeError, match="invalid JSON"):
            llm.main_loop()
        spy.assert_not_called()


@patch("src.llm.requests.post")
def test_missing_response_key_does_not_call_add_response_to_json(mock_post):
    mock_post.return_value = _ok_json_response({"not_response": "x"})

    llm = LLM(transcript_text="hello", target_fields={"f": None})

    with patch.object(LLM, "add_response_to_json") as spy:
        with pytest.raises(RuntimeError, match="missing 'response' key"):
            llm.main_loop()
        spy.assert_not_called()


@patch("src.llm.requests.post")
def test_non_string_response_field_raises(mock_post):
    mock_post.return_value = _ok_json_response({"response": 123})

    llm = LLM(transcript_text="hello", target_fields={"f": None})

    with patch.object(LLM, "add_response_to_json") as spy:
        with pytest.raises(RuntimeError, match="must be a string"):
            llm.main_loop()
        spy.assert_not_called()


@patch("src.llm.requests.post")
def test_connection_error_exhausts_retries(mock_post):
    mock_post.side_effect = requests.exceptions.ConnectionError("refused")

    llm = LLM(transcript_text="hello", target_fields={"f": None})

    with pytest.raises(ConnectionError, match="Could not connect to Ollama"):
        llm.main_loop()

    assert mock_post.call_count == OLLAMA_MAX_ATTEMPTS
