"""Tests for app.services.llm: config checks, both LLM classes, JSON parsing.

Nothing here reaches a real server. Ollama is faked at requests.request and the
OpenAI compatible class at its SDK client.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import openai
import pytest
import requests

from app.services.llm import (
    LLMAuthError,
    LLMConfigError,
    LLMProvider,
    LLMResponseError,
    LLMUnavailableError,
    create_llm,
)
from app.services.llm.base import parse_json_object
from app.services.llm.factory import is_local_url
from app.services.llm.ollama import OPTIONS, OllamaLLM
from app.services.llm.openai_compatible import OpenAICompatibleLLM

SCHEMA = {"type": "object", "properties": {"name": {"type": "string"}}}


def _cfg(**overrides):
    """Config with every LLM setting at its default, plus overrides."""
    values = {
        "OLLAMA_HOST": "http://ollama:11434",
        "OLLAMA_MODEL": "qwen2.5:1.5b",
        "OLLAMA_TIMEOUT": 300,
        "LLM_PROVIDER": "ollama",
        "LLM_BASE_URL": "",
        "LLM_API_KEY": "",
        "OPENAI_API_KEY": "",
        "GEMINI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "LLM_MODEL": "",
        "LLM_TIMEOUT": "",
        "LLM_MAX_RETRIES": "",
        "LLM_ALLOW_EXTERNAL": "false",
        "LLM_STRUCTURED_OUTPUT": "",
        "LLM_MAX_TOKENS": "",
        "LLM_TEMPERATURE": "0",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


# ---------------------------------------------------------------------------
# factory.create_llm
# ---------------------------------------------------------------------------

class TestCreateLLM:

    def test_default_is_ollama_from_ollama_settings(self):
        llm = create_llm(_cfg())
        assert isinstance(llm, OllamaLLM)
        assert llm.host == "http://ollama:11434"
        assert llm.model == "qwen2.5:1.5b"
        assert llm.timeout == 300

    def test_llm_settings_override_ollama_ones(self):
        llm = create_llm(_cfg(LLM_BASE_URL="http://gpu-box:11434", LLM_MODEL="llama3:8b", LLM_TIMEOUT="60"))
        assert llm.host == "http://gpu-box:11434"
        assert llm.model == "llama3:8b"
        assert llm.timeout == 60

    @pytest.mark.parametrize("provider", list(LLMProvider))
    def test_every_provider_builds(self, provider):
        """Catches an enum value added without a matching case in create_llm."""
        llm = create_llm(_cfg(
            LLM_PROVIDER=provider.value, LLM_BASE_URL="http://local-llm:8000/v1", LLM_MODEL="m",
            LLM_API_KEY="k",
        ))
        assert llm.provider is provider

    def test_unknown_provider(self):
        with pytest.raises(LLMConfigError, match="LLM_PROVIDER='mystery'"):
            create_llm(_cfg(LLM_PROVIDER="mystery"))

    def test_custom_needs_base_url(self):
        with pytest.raises(LLMConfigError, match="LLM_BASE_URL"):
            create_llm(_cfg(LLM_PROVIDER="custom", LLM_MODEL="m"))

    def test_custom_needs_model(self):
        with pytest.raises(LLMConfigError, match="LLM_MODEL"):
            create_llm(_cfg(LLM_PROVIDER="custom", LLM_BASE_URL="http://vllm:8000/v1"))

    def test_custom_on_local_network_needs_no_key_or_flag(self):
        llm = create_llm(_cfg(LLM_PROVIDER="custom", LLM_BASE_URL="http://vllm:8000/v1", LLM_MODEL="qwen"))
        assert isinstance(llm, OpenAICompatibleLLM)
        assert llm.provider == "custom"
        assert llm.structured_output is True

    def test_hosted_needs_its_own_key(self):
        with pytest.raises(LLMConfigError, match="GEMINI_API_KEY"):
            create_llm(_cfg(LLM_PROVIDER="gemini", LLM_MODEL="g", LLM_ALLOW_EXTERNAL="true"))

    def test_hosted_falls_back_to_llm_api_key(self):
        llm = create_llm(_cfg(LLM_PROVIDER="openai", LLM_MODEL="o", LLM_API_KEY="k", LLM_ALLOW_EXTERNAL="true"))
        assert llm.client.api_key == "k"

    def test_external_refused_without_flag(self):
        with pytest.raises(LLMConfigError, match="LLM_ALLOW_EXTERNAL"):
            create_llm(_cfg(LLM_PROVIDER="openai", LLM_MODEL="o", OPENAI_API_KEY="k"))

    def test_external_custom_refused_without_flag(self):
        with pytest.raises(LLMConfigError, match="LLM_ALLOW_EXTERNAL"):
            create_llm(_cfg(LLM_PROVIDER="custom", LLM_BASE_URL="https://api.groq.com/openai/v1", LLM_MODEL="m"))

    def test_hosted_preset_url_and_key(self):
        llm = create_llm(_cfg(LLM_PROVIDER="gemini", LLM_MODEL="g", GEMINI_API_KEY="gk", LLM_ALLOW_EXTERNAL="true"))
        assert llm.base_url.startswith("https://generativelanguage.googleapis.com")
        assert llm.client.api_key == "gk"
        assert llm.temperature == 0.0
        assert llm.max_tokens is None

    def test_anthropic_preset_defaults_and_overrides(self):
        base = {"LLM_PROVIDER": "anthropic", "LLM_MODEL": "c", "ANTHROPIC_API_KEY": "ak", "LLM_ALLOW_EXTERNAL": "true"}
        llm = create_llm(_cfg(**base))
        assert llm.structured_output is False
        assert llm.max_tokens == 12288

        llm = create_llm(_cfg(**base, LLM_STRUCTURED_OUTPUT="true", LLM_MAX_TOKENS="4000"))
        assert llm.structured_output is True
        assert llm.max_tokens == 4000

    def test_empty_temperature_sends_none(self):
        llm = create_llm(_cfg(LLM_PROVIDER="custom", LLM_BASE_URL="http://vllm:8000/v1", LLM_MODEL="m",
                              LLM_TEMPERATURE=""))
        assert llm.temperature is None

    @pytest.mark.parametrize("setting, value", [
        ("LLM_TIMEOUT", "soon"),
        ("LLM_MAX_TOKENS", "lots"),
        ("LLM_TEMPERATURE", "warm"),
        ("LLM_STRUCTURED_OUTPUT", "maybe"),
        ("LLM_ALLOW_EXTERNAL", "sure"),
    ])
    def test_bad_values_name_the_setting(self, setting, value):
        values = {"LLM_PROVIDER": "custom", "LLM_BASE_URL": "https://example.com/v1", "LLM_MODEL": "m",
                  "LLM_ALLOW_EXTERNAL": "true"}
        values[setting] = value
        with pytest.raises(LLMConfigError, match=setting):
            create_llm(_cfg(**values))

    @pytest.mark.parametrize("url", ["vllm:8000/v1", "ftp://host", "http://"])
    def test_bad_url(self, url):
        with pytest.raises(LLMConfigError, match="not a valid URL"):
            create_llm(_cfg(LLM_PROVIDER="custom", LLM_BASE_URL=url, LLM_MODEL="m"))


@pytest.mark.parametrize("url, local", [
    ("http://localhost:8000/v1", True),
    ("http://127.0.0.1:1234/v1", True),
    ("http://192.168.1.20:8000/v1", True),
    ("http://10.0.0.5:8000/v1", True),
    ("http://vllm:8000/v1", True),
    ("http://host.docker.internal:1234/v1", True),
    ("http://gpu.local:8000/v1", True),
    ("https://api.openai.com/v1", False),
    ("http://8.8.8.8:8000/v1", False),
])
def test_is_local_url(url, local):
    assert is_local_url(url) is local


# ---------------------------------------------------------------------------
# base.parse_json_object
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ('{"a": 1}', '{"a": 1}'),
    ('  {"a": 1}\n', '{"a": 1}'),
    ('```json\n{"a": 1}\n```', '{"a": 1}'),
    ('Here you go: {"a": {"b": 2}} Done.', '{"a": {"b": 2}}'),
])
def test_parse_json_object(raw, expected):
    assert parse_json_object(raw) == expected


@pytest.mark.parametrize("raw", ["", "no json here", "[1, 2]", "{broken"])
def test_parse_json_object_rejects(raw):
    with pytest.raises(LLMResponseError):
        parse_json_object(raw)


# ---------------------------------------------------------------------------
# OllamaLLM
# ---------------------------------------------------------------------------

def _response(status_code=200, json_data=None, text=""):
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_data or {}
    m.text = text
    return m


class TestOllamaLLM:

    def _llm(self):
        return OllamaLLM(host="http://ollama:11434/", model="qwen2.5:1.5b", timeout=300)

    def test_generate_sends_schema_as_format(self, monkeypatch):
        calls = []

        def fake(method, url, **kwargs):
            calls.append((method, url, kwargs))
            return _response(json_data={"response": '{"name": "Ana"}'})

        monkeypatch.setattr("app.services.llm.ollama.requests.request", fake)

        assert self._llm().generate_json("prompt", SCHEMA) == '{"name": "Ana"}'
        method, url, kwargs = calls[0]
        assert (method, url) == ("post", "http://ollama:11434/api/generate")
        assert kwargs["timeout"] == 300
        assert kwargs["json"]["format"] == SCHEMA
        assert kwargs["json"]["model"] == "qwen2.5:1.5b"
        assert kwargs["json"]["options"] == OPTIONS

    def test_model_override_for_one_call(self, monkeypatch):
        sent = {}

        def fake(method, url, **kwargs):
            sent.update(kwargs["json"])
            return _response(json_data={"response": "{}"})

        monkeypatch.setattr("app.services.llm.ollama.requests.request", fake)
        llm = self._llm()
        llm.generate_json("prompt", SCHEMA, "llama3:8b")
        assert sent["model"] == "llama3:8b"
        assert llm.model == "qwen2.5:1.5b"

    @pytest.mark.parametrize("failure, error", [
        (requests.exceptions.ConnectionError("down"), LLMUnavailableError),
        (requests.exceptions.ReadTimeout("slow"), LLMUnavailableError),
        (_response(status_code=500, text="boom"), LLMUnavailableError),
        (_response(status_code=404, text="model not found"), LLMResponseError),
    ])
    def test_failures_become_llm_errors(self, monkeypatch, failure, error):
        def fake(method, url, **kwargs):
            if isinstance(failure, Exception):
                raise failure
            return failure

        monkeypatch.setattr("app.services.llm.ollama.requests.request", fake)
        with pytest.raises(error):
            self._llm().generate_json("prompt", SCHEMA)

    def test_health_unhealthy_when_down(self, monkeypatch):
        def fake(method, url, **kwargs):
            raise requests.exceptions.ConnectionError("down")

        monkeypatch.setattr("app.services.llm.ollama.requests.request", fake)
        health = self._llm().health()
        assert health.status == "unhealthy"
        assert health.provider == "ollama"
        assert "Could not reach Ollama" in health.detail


# ---------------------------------------------------------------------------
# OpenAICompatibleLLM
# ---------------------------------------------------------------------------

def _completion(content='{"name": "Ana"}', finish_reason="stop"):
    message = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


def _openai_llm(**kwargs):
    llm = OpenAICompatibleLLM(
        provider=LLMProvider.custom, base_url="http://vllm:8000/v1", api_key="", model="qwen", timeout=60, **kwargs
    )
    llm.client = MagicMock()
    llm.client.chat.completions.create.return_value = _completion()
    return llm


_REQUEST = httpx.Request("POST", "http://vllm:8000/v1/chat/completions")


def _status_error(cls, code):
    return cls("error", response=httpx.Response(code, request=_REQUEST), body=None)


class TestOpenAICompatibleLLM:

    def test_structured_output_sends_schema(self):
        llm = _openai_llm(structured_output=True, temperature=0.0)
        assert llm.generate_json("prompt", SCHEMA) == '{"name": "Ana"}'

        kwargs = llm.client.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "qwen"
        assert kwargs["messages"] == [{"role": "user", "content": "prompt"}]
        assert kwargs["response_format"]["json_schema"]["schema"] == SCHEMA
        assert kwargs["temperature"] == 0.0
        assert "max_tokens" not in kwargs

    def test_unset_options_are_not_sent(self):
        llm = _openai_llm(structured_output=False)
        llm.generate_json("prompt", SCHEMA)
        kwargs = llm.client.chat.completions.create.call_args.kwargs
        assert "response_format" not in kwargs
        assert "temperature" not in kwargs
        assert "max_tokens" not in kwargs

    def test_max_tokens_and_model_override(self):
        llm = _openai_llm(max_tokens=4000)
        llm.generate_json("prompt", SCHEMA, "bigger-model")
        kwargs = llm.client.chat.completions.create.call_args.kwargs
        assert kwargs["max_tokens"] == 4000
        assert kwargs["model"] == "bigger-model"

    def test_fenced_answer_is_cleaned(self):
        llm = _openai_llm()
        llm.client.chat.completions.create.return_value = _completion('```json\n{"a": 1}\n```')
        assert llm.generate_json("prompt", SCHEMA) == '{"a": 1}'

    def test_cut_off_answer(self):
        llm = _openai_llm()
        llm.client.chat.completions.create.return_value = _completion('{"a": ', finish_reason="length")
        with pytest.raises(LLMResponseError, match="LLM_MAX_TOKENS"):
            llm.generate_json("prompt", SCHEMA)

    def test_no_choices(self):
        llm = _openai_llm()
        llm.client.chat.completions.create.return_value = SimpleNamespace(choices=[])
        with pytest.raises(LLMResponseError):
            llm.generate_json("prompt", SCHEMA)

    @pytest.mark.parametrize("failure, error", [
        (_status_error(openai.AuthenticationError, 401), LLMAuthError),
        (_status_error(openai.PermissionDeniedError, 403), LLMAuthError),
        (_status_error(openai.RateLimitError, 429), LLMUnavailableError),
        (_status_error(openai.InternalServerError, 500), LLMUnavailableError),
        (_status_error(openai.BadRequestError, 400), LLMResponseError),
        (openai.APITimeoutError(request=_REQUEST), LLMUnavailableError),
        (openai.APIConnectionError(request=_REQUEST), LLMUnavailableError),
    ])
    def test_sdk_errors_become_llm_errors(self, failure, error):
        llm = _openai_llm()
        llm.client.chat.completions.create.side_effect = failure
        with pytest.raises(error):
            llm.generate_json("prompt", SCHEMA)

    def test_errors_carry_status_codes(self):
        llm = _openai_llm()
        llm.client.chat.completions.create.side_effect = openai.APIConnectionError(request=_REQUEST)
        with pytest.raises(LLMUnavailableError) as info:
            llm.generate_json("prompt", SCHEMA)
        assert info.value.status_code == 503
        assert info.value.error_code == "LLM_UNAVAILABLE"

    def test_list_models_and_health(self):
        llm = _openai_llm()
        llm.client.with_options.return_value.models.list.return_value = [SimpleNamespace(id="qwen")]

        assert [m.name for m in llm.list_models()] == ["qwen"]
        health = llm.health()
        assert health.status == "healthy"
        assert health.provider == "custom"
        assert health.models_available[0].name == "qwen"

    def test_health_unhealthy_when_down(self):
        llm = _openai_llm()
        llm.client.with_options.return_value.models.list.side_effect = openai.APIConnectionError(request=_REQUEST)
        health = llm.health()
        assert health.status == "unhealthy"
        assert "Could not reach custom" in health.detail
