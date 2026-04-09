import pytest
import requests

from src.llm import LLM


class DummyResponse:
    def __init__(self, status_error=None, json_data=None, json_error=None):
        self._status_error = status_error
        self._json_data = json_data
        self._json_error = json_error

    def raise_for_status(self):
        if self._status_error:
            raise self._status_error

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._json_data


def make_llm():
    return LLM(transcript_text="incident text", target_fields={"name": "string"})


def test_llm_timeout_raises_timeouterror(monkeypatch):
    def fake_post(*args, **kwargs):
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(TimeoutError, match="timed out"):
        make_llm().main_loop()


def test_llm_http_error_raises_runtimeerror(monkeypatch):
    http_error = requests.exceptions.HTTPError("500 Server Error")

    def fake_post(*args, **kwargs):
        return DummyResponse(status_error=http_error)

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(RuntimeError, match="HTTP error"):
        make_llm().main_loop()


def test_llm_invalid_json_raises_valueerror(monkeypatch):
    def fake_post(*args, **kwargs):
        return DummyResponse(json_error=ValueError("bad json"))

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(ValueError, match="Invalid JSON response"):
        make_llm().main_loop()


def test_llm_missing_response_key_raises_valueerror(monkeypatch):
    def fake_post(*args, **kwargs):
        return DummyResponse(json_data={"other": "value"})

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(ValueError, match="missing 'response' key"):
        make_llm().main_loop()
