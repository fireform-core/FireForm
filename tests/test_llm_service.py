"""Tests for app.services.llm: settings, both LLM classes, JSON parsing.

Nothing here reaches a real server. Ollama is faked at requests.request and the
OpenAI compatible class at its SDK client. The registry and validator have
their own file, test_llm_registry.py.
"""

import os
import stat
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import openai
import pytest
import requests
from cryptography.fernet import Fernet

from app.services.llm import (
    LLMAuthError,
    LLMConfigError,
    LLMSecretKeyError,
    LLMModelNotFoundError,
    LLMProvider,
    LLMRateLimitError,
    LLMResponseError,
    LLMUnavailableError,
    create_llm,
    load_settings,
)
from app.services.llm.base import parse_json_object
from app.services.llm.ollama import OPTIONS, OllamaLLM
from app.services.llm.openai_compatible import OpenAICompatibleLLM
from app.services.llm.settings import is_local_url

SCHEMA = {"type": "object", "properties": {"name": {"type": "string"}}}

LOCAL_URL = "http://local-llm:8000/v1"


def _cfg(providers: dict | None = None, **overrides):
    """Config with every LLM setting at its default, plus overrides.

    providers maps a provider name to its <PREFIX>_* settings without the
    prefix, such as {"gemini": {"API_KEY": "k", "MODELS": "g"}}.
    """
    env = {"ollama": {"BASE_URL": "http://ollama:11434", "MODELS": "*"}}
    for name, values in (providers or {}).items():
        env[name] = {**env.get(name, {}), **values}
    values = {
        "OLLAMA_MODEL": "qwen2.5:1.5b",
        "OLLAMA_TIMEOUT": 300,
        "LLM_PROVIDER": "ollama",
        "LLM_MODEL": "",
        "LLM_TIMEOUT": "",
        "LLM_MAX_RETRIES": "",
        "LLM_ALLOW_EXTERNAL": "false",
        "LLM_TEMPERATURE": "0",
        "LLM_PROVIDER_ENV": env,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _only(provider: str, settings: dict, **overrides):
    """Config with one provider as the default and Ollama off."""
    return _cfg({"ollama": {"MODELS": ""}, provider: settings}, LLM_PROVIDER=provider, **overrides)


# ---------------------------------------------------------------------------
# settings.load_settings + factory.create_llm
# ---------------------------------------------------------------------------

class TestLoadSettings:

    def test_default_is_ollama_listing_every_model(self):
        settings = load_settings(_cfg())
        assert list(settings.providers) == [LLMProvider.ollama]
        assert settings.default_provider is LLMProvider.ollama
        assert settings.default_model == "qwen2.5:1.5b"
        ollama = settings.providers[LLMProvider.ollama]
        assert ollama.models.wildcard
        assert ollama.timeout == 300
        assert settings.warnings == ()

        llm = create_llm(ollama)
        assert isinstance(llm, OllamaLLM)
        assert llm.host == "http://ollama:11434"
        assert llm.model == "qwen2.5:1.5b"

    def test_provider_settings_repr_never_includes_api_key(self):
        secret = "provider-secret-value"
        settings = load_settings(
            _only("gemini", {"API_KEY": secret, "MODELS": "g"}, LLM_ALLOW_EXTERNAL="true")
        )

        assert secret not in repr(settings.providers[LLMProvider.gemini])

    def test_llm_model_and_timeout_override(self):
        settings = load_settings(_cfg(LLM_MODEL="llama3:8b", LLM_TIMEOUT="60"))
        assert settings.default_model == "llama3:8b"
        assert settings.providers[LLMProvider.ollama].timeout == 60

    @pytest.mark.parametrize("provider", list(LLMProvider))
    def test_every_provider_builds(self, provider):
        """Catches an enum value added without a row in SPECS."""
        settings = load_settings(_only(provider.value, {"BASE_URL": LOCAL_URL, "API_KEY": "k", "MODELS": "m"}))
        assert settings.default_provider is provider
        assert create_llm(settings.providers[provider]).provider is provider

    def test_several_providers_side_by_side(self):
        settings = load_settings(_cfg(
            {"gemini": {"API_KEY": "gk", "MODELS": "g1,g2"}, "custom": {"BASE_URL": LOCAL_URL, "MODELS": "*"}},
            LLM_ALLOW_EXTERNAL="true",
        ))
        assert set(settings.providers) == {LLMProvider.ollama, LLMProvider.gemini, LLMProvider.custom}
        assert settings.default_provider is LLMProvider.ollama
        assert settings.providers[LLMProvider.gemini].default_model == "g1"
        assert settings.providers[LLMProvider.custom].default_model is None

    def test_provider_without_models_is_off(self):
        settings = load_settings(_cfg({"openai": {"MODELS": ""}}))
        assert LLMProvider.openai not in settings.providers
        assert settings.warnings == ()

    def test_key_without_models_warns(self):
        settings = load_settings(_cfg({"openai": {"API_KEY": "k"}}))
        assert LLMProvider.openai not in settings.providers
        assert any("OPENAI_MODELS is empty" in w for w in settings.warnings)

    def test_unknown_provider(self):
        with pytest.raises(LLMConfigError, match="LLM_PROVIDER='mystery'"):
            load_settings(_cfg(LLM_PROVIDER="mystery"))

    def test_default_provider_must_be_on(self):
        with pytest.raises(LLMConfigError, match="GEMINI_MODELS is empty") as info:
            load_settings(_cfg(LLM_PROVIDER="gemini", LLM_MODEL="g"))
        assert "Add GEMINI_MODELS=g" in info.value.message

    def test_default_key_without_models_suggests_the_fix(self):
        """The case that used to crash startup with no hint."""
        cfg = _only("gemini", {"API_KEY": "k"}, LLM_MODEL="gemini-3.8-flash-lite", LLM_ALLOW_EXTERNAL="true")
        with pytest.raises(LLMConfigError) as info:
            load_settings(cfg)
        assert info.value.message == (
            "GEMINI_API_KEY is set but GEMINI_MODELS is empty. Add GEMINI_MODELS=gemini-3.8-flash-lite, "
            "a comma separated list, or * for every model gemini lists."
        )

    def test_ollama_can_be_off(self):
        settings = load_settings(_only("custom", {"BASE_URL": LOCAL_URL, "MODELS": "qwen"}))
        assert list(settings.providers) == [LLMProvider.custom]

    def test_mistake_in_default_provider_stops_startup(self):
        with pytest.raises(LLMConfigError, match="GEMINI_API_KEY is needed"):
            load_settings(_only("gemini", {"MODELS": "g"}, LLM_ALLOW_EXTERNAL="true"))

    def test_mistake_in_other_provider_turns_it_off(self):
        settings = load_settings(_cfg({"gemini": {"MODELS": "g"}}, LLM_ALLOW_EXTERNAL="true"))
        assert LLMProvider.gemini not in settings.providers
        assert settings.warnings == (
            "gemini is off: GEMINI_API_KEY is needed. Add it, or empty GEMINI_MODELS to turn gemini off.",
        )

    def test_custom_needs_base_url(self):
        with pytest.raises(LLMConfigError, match="CUSTOM_BASE_URL is needed"):
            load_settings(_only("custom", {"MODELS": "m"}))

    def test_custom_on_local_network_needs_no_key_or_flag(self):
        settings = load_settings(_only("custom", {"BASE_URL": LOCAL_URL, "MODELS": "qwen"}))
        llm = create_llm(settings.providers[LLMProvider.custom])
        assert isinstance(llm, OpenAICompatibleLLM)
        assert llm.structured_output is True
        assert llm.model == "qwen"

    def test_external_refused_without_flag(self):
        with pytest.raises(LLMConfigError, match="LLM_ALLOW_EXTERNAL"):
            load_settings(_only("openai", {"API_KEY": "k", "MODELS": "o"}))

    def test_external_non_default_refused_with_warning(self):
        settings = load_settings(_cfg({"openai": {"API_KEY": "k", "MODELS": "o"}}))
        assert LLMProvider.openai not in settings.providers
        assert "LLM_ALLOW_EXTERNAL" in settings.warnings[0]

    def test_external_custom_refused_without_flag(self):
        with pytest.raises(LLMConfigError, match="LLM_ALLOW_EXTERNAL"):
            load_settings(_only("custom", {"BASE_URL": "https://api.groq.com/openai/v1", "MODELS": "m"}))

    def test_llm_model_must_be_in_the_list(self):
        with pytest.raises(LLMConfigError, match="LLM_MODEL=other is not in CUSTOM_MODELS"):
            load_settings(_only("custom", {"BASE_URL": LOCAL_URL, "MODELS": "a,b"}, LLM_MODEL="other"))

    def test_wildcard_default_needs_llm_model(self):
        with pytest.raises(LLMConfigError, match="Set LLM_MODEL"):
            load_settings(_only("custom", {"BASE_URL": LOCAL_URL, "MODELS": "*"}))
        settings = load_settings(_only("custom", {"BASE_URL": LOCAL_URL, "MODELS": "*"}, LLM_MODEL="any"))
        assert settings.default_model == "any"

    def test_ollama_model_outside_list_falls_back_to_first(self):
        settings = load_settings(_cfg({"ollama": {"MODELS": "llama3:8b,mistral:7b"}}))
        assert settings.default_model == "llama3:8b"

    def test_hosted_preset_url_and_key(self):
        settings = load_settings(_only("gemini", {"API_KEY": "gk", "MODELS": "g"}, LLM_ALLOW_EXTERNAL="true"))
        llm = create_llm(settings.providers[LLMProvider.gemini])
        assert llm.base_url.startswith("https://generativelanguage.googleapis.com")
        assert llm.client.api_key == "gk"
        assert llm.temperature == 0.0
        assert llm.max_tokens is None

    def test_gemini_ids_lose_their_prefix(self):
        settings = load_settings(_only("gemini", {"API_KEY": "gk", "MODELS": "g"}, LLM_ALLOW_EXTERNAL="true"))
        llm = create_llm(settings.providers[LLMProvider.gemini])
        llm.client = MagicMock()
        llm.client.with_options.return_value.models.list.return_value = [
            SimpleNamespace(id="models/gemini-2.5-flash"), SimpleNamespace(id="gemini-3.8-flash"),
        ]
        assert [m.name for m in llm.list_models()] == ["gemini-2.5-flash", "gemini-3.8-flash"]

    def test_anthropic_sends_version_header(self):
        settings = load_settings(_only("anthropic", {"API_KEY": "ak", "MODELS": "c"}, LLM_ALLOW_EXTERNAL="true"))
        llm = create_llm(settings.providers[LLMProvider.anthropic])
        assert llm.client.default_headers["anthropic-version"] == "2023-06-01"

    def test_anthropic_preset_defaults_and_overrides(self):
        base = {"API_KEY": "ak", "MODELS": "c"}
        settings = load_settings(_only("anthropic", base, LLM_ALLOW_EXTERNAL="true"))
        anthropic = settings.providers[LLMProvider.anthropic]
        assert anthropic.structured_output is False
        assert anthropic.max_tokens == 12288

        overrides = {**base, "STRUCTURED_OUTPUT": "true", "MAX_TOKENS": "4000"}
        settings = load_settings(_only("anthropic", overrides, LLM_ALLOW_EXTERNAL="true"))
        anthropic = settings.providers[LLMProvider.anthropic]
        assert anthropic.structured_output is True
        assert anthropic.max_tokens == 4000

    def test_empty_temperature_sends_none(self):
        settings = load_settings(_only("custom", {"BASE_URL": LOCAL_URL, "MODELS": "m"}, LLM_TEMPERATURE=""))
        assert settings.providers[LLMProvider.custom].temperature is None

    @pytest.mark.parametrize("setting, value", [
        ("LLM_TIMEOUT", "soon"),
        ("LLM_TEMPERATURE", "warm"),
        ("LLM_ALLOW_EXTERNAL", "sure"),
        ("CUSTOM_MAX_TOKENS", "lots"),
        ("CUSTOM_STRUCTURED_OUTPUT", "maybe"),
    ])
    def test_bad_values_name_the_setting(self, setting, value):
        custom = {"BASE_URL": LOCAL_URL, "MODELS": "m"}
        overrides = {}
        if setting.startswith("CUSTOM_"):
            custom[setting.removeprefix("CUSTOM_")] = value
        else:
            overrides[setting] = value
        with pytest.raises(LLMConfigError, match=setting):
            load_settings(_only("custom", custom, **overrides))

    @pytest.mark.parametrize("url", ["vllm:8000/v1", "ftp://host", "http://"])
    def test_bad_url(self, url):
        with pytest.raises(LLMConfigError, match="CUSTOM_BASE_URL=.* is not a valid URL"):
            load_settings(_only("custom", {"BASE_URL": url, "MODELS": "m"}))


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
        (_response(status_code=404, json_data={"error": "model 'qwen2.5:1.5b' not found"}), LLMModelNotFoundError),
        (_response(status_code=400, json_data={"error": "invalid format"}), LLMResponseError),
    ])
    def test_failures_become_llm_errors(self, monkeypatch, failure, error):
        def fake(method, url, **kwargs):
            if isinstance(failure, Exception):
                raise failure
            return failure

        monkeypatch.setattr("app.services.llm.ollama.requests.request", fake)
        with pytest.raises(error):
            self._llm().generate_json("prompt", SCHEMA)

    def test_killed_runner_says_out_of_memory(self, monkeypatch):
        body = {"error": "llama-server process has terminated: signal: killed"}
        monkeypatch.setattr(
            "app.services.llm.ollama.requests.request",
            lambda method, url, **kwargs: _response(status_code=500, json_data=body),
        )
        with pytest.raises(LLMUnavailableError, match="Ollama ran out of memory loading qwen2.5:1.5b"):
            self._llm().generate_json("prompt", SCHEMA)

    def test_health_unhealthy_when_down(self, monkeypatch):
        def fake(method, url, **kwargs):
            raise requests.exceptions.ConnectionError("down")

        monkeypatch.setattr("app.services.llm.ollama.requests.request", fake)
        health = self._llm().health()
        assert health.status == "unhealthy"
        assert health.provider == "ollama"
        assert "Could not reach Ollama" in health.detail

    def test_list_models_marks_every_tag_as_installed(self, monkeypatch):
        """Each model from /api/tags carries installed=True."""
        tags = {
            "models": [
                {"name": "qwen2.5:1.5b", "size": 987_654_321, "details": {"quantization_level": "Q4_K_M"}},
                {"name": "llama3:8b", "size": 4_700_000_000},
            ]
        }

        def fake(method, url, **kwargs):
            if url.endswith("/api/tags"):
                return _response(json_data=tags)
            if url.endswith("/api/ps"):
                return _response(json_data={"models": [{"name": "qwen2.5:1.5b"}]})
            raise AssertionError(f"unexpected {method} {url}")

        monkeypatch.setattr("app.services.llm.ollama.requests.request", fake)
        models = self._llm().list_models()
        assert [m.name for m in models] == ["qwen2.5:1.5b", "llama3:8b"]
        assert all(m.installed is True for m in models)
        assert models[0].loaded is True
        assert models[1].loaded is False


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


def _status_error(cls, code, body=None):
    return cls("error", response=httpx.Response(code, request=_REQUEST), body=body)


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
        with pytest.raises(LLMResponseError, match="CUSTOM_MAX_TOKENS"):
            llm.generate_json("prompt", SCHEMA)

    def test_no_choices(self):
        llm = _openai_llm()
        llm.client.chat.completions.create.return_value = SimpleNamespace(choices=[])
        with pytest.raises(LLMResponseError):
            llm.generate_json("prompt", SCHEMA)

    @pytest.mark.parametrize("failure, error", [
        (_status_error(openai.AuthenticationError, 401), LLMAuthError),
        (_status_error(openai.PermissionDeniedError, 403), LLMAuthError),
        (_status_error(openai.RateLimitError, 429), LLMRateLimitError),
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

    def test_gemini_bad_key_is_an_auth_error(self):
        """Gemini answers a bad key with 400 and its body is a list."""
        llm = OpenAICompatibleLLM(LLMProvider.gemini, "https://g.example/v1", "bad", "g", 60)
        llm.client = MagicMock()
        body = [{"error": {"code": 400, "message": "Please pass a valid API key.", "status": "INVALID_ARGUMENT"}}]
        llm.client.chat.completions.create.side_effect = _status_error(openai.BadRequestError, 400, body)
        with pytest.raises(LLMAuthError) as info:
            llm.generate_json("prompt", SCHEMA)
        assert info.value.message == "gemini rejected the API key: Please pass a valid API key. Check GEMINI_API_KEY."
        assert info.value.error_code == "LLM_AUTH_FAILED"

    def test_api_key_in_provider_error_is_redacted(self):
        secret = "sk-example-secret-value"
        llm = OpenAICompatibleLLM(LLMProvider.openai, "https://api.example/v1", secret, "gpt", 60)
        llm.client = MagicMock()
        llm.client.chat.completions.create.side_effect = _status_error(
            openai.AuthenticationError, 401, {"error": {"message": f"Invalid key {secret}"}}
        )
        with pytest.raises(LLMAuthError) as info:
            llm.generate_json("prompt", SCHEMA)
        assert secret not in info.value.message
        assert "[redacted]" in info.value.message

    def test_non_string_error_redaction_key_is_ignored(self):
        from app.services.llm.openai_compatible import _reason

        error = _status_error(openai.BadRequestError, 400, {"error": {"message": "Bad request"}})
        assert _reason(error, MagicMock()) == "Bad request"

    @pytest.mark.parametrize("secret", ["short", "not-needed"])
    def test_short_and_placeholder_keys_are_not_used_for_redaction(self, secret):
        from app.services.llm.openai_compatible import _reason

        error = _status_error(
            openai.BadRequestError,
            400,
            {"error": {"message": f"Request mentioned {secret}"}},
        )
        assert _reason(error, secret) == f"Request mentioned {secret}"

    def test_missing_model_names_it(self):
        llm = _openai_llm()
        body = {"error": {"message": "The model `nope` does not exist"}}
        llm.client.chat.completions.create.side_effect = _status_error(openai.NotFoundError, 404, body)
        with pytest.raises(LLMModelNotFoundError) as info:
            llm.generate_json("prompt", SCHEMA, "nope")
        assert info.value.message == "custom has no model nope: The model `nope` does not exist"

    def test_404_on_model_list_points_at_base_url(self):
        llm = _openai_llm()
        llm.client.with_options.return_value.models.list.side_effect = _status_error(openai.NotFoundError, 404)
        with pytest.raises(LLMResponseError, match="Check CUSTOM_BASE_URL"):
            llm.list_models()

    def test_anthropic_error_body(self):
        llm = _openai_llm()
        body = {"type": "error", "error": {"type": "invalid_request_error", "message": "max_tokens: too large"}}
        llm.client.chat.completions.create.side_effect = _status_error(openai.BadRequestError, 400, body)
        with pytest.raises(LLMResponseError) as info:
            llm.generate_json("prompt", SCHEMA)
        assert info.value.message == "custom refused the request with 400: max_tokens: too large"

    def test_non_json_answer_names_provider_and_model(self):
        llm = _openai_llm()
        llm.client.chat.completions.create.return_value = _completion("sorry, no")
        with pytest.raises(LLMResponseError, match="custom model qwen: Model did not return a JSON object"):
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
        assert "Check CUSTOM_BASE_URL" in health.detail


# ---------------------------------------------------------------------------
# OllamaLLM.pull_model — streaming, no real network
# ---------------------------------------------------------------------------

class _FakeStreamResponse:
    """Simulates requests.Response.iter_content for a pull stream."""

    def __init__(self, chunks: list[bytes], raise_at: int | None = None, raise_exc=None):
        self._chunks = chunks
        self._raise_at = raise_at  # raise raise_exc after this many chunks
        self._raise_exc = raise_exc
        self.status_code = 200

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=None):
        for i, chunk in enumerate(self._chunks):
            if self._raise_at is not None and i >= self._raise_at:
                raise self._raise_exc
            yield chunk

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def _pull_llm(pull_timeout=30):
    return OllamaLLM(host="http://ollama:11434", model="qwen2.5:1.5b", timeout=300, pull_timeout=pull_timeout)


class TestOllamaPull:

    def test_happy_path_streams_lines_and_calls_callback(self, monkeypatch):
        """Lines are forwarded; callback fires once on success."""
        import json

        chunks = [
            b'{"status": "pulling manifest"}\n',
            b'{"status": "downloading", "completed": 50, "total": 100}\n',
            b'{"status": "success"}\n',
        ]
        resp = _FakeStreamResponse(chunks)
        monkeypatch.setattr("app.services.llm.ollama.requests.post", lambda *a, **k: resp)

        fired = []
        lines = list(_pull_llm().pull_model("qwen2.5:3b", on_success=lambda: fired.append(1)))

        parsed = [json.loads(line) for line in lines]
        assert parsed[0]["status"] == "pulling manifest"
        assert parsed[-1]["status"] == "success"
        assert fired == [1]

    def test_error_after_success_suppresses_success_and_callback(self, monkeypatch):
        """An error anywhere in the stream prevents success, even after Ollama's success line."""
        import json

        chunks = [
            b'{"status": "pulling manifest"}\n',
            b'{"status": "success"}\n',
            b'{"error": "pull access denied"}\n',
        ]
        resp = _FakeStreamResponse(chunks)
        monkeypatch.setattr("app.services.llm.ollama.requests.post", lambda *a, **k: resp)

        fired = []
        lines = list(_pull_llm().pull_model("secret:model", on_success=lambda: fired.append(1)))

        parsed = [json.loads(line) for line in lines]
        statuses = [p.get("status") for p in parsed]
        assert "success" not in statuses
        assert fired == []

    def test_read_timeout_mid_stream_yields_error_no_success(self, monkeypatch):
        """A ReadTimeout after the stream starts produces an error line, not success."""
        import json

        chunks = [b'{"status": "downloading"}\n', b"more"]
        resp = _FakeStreamResponse(chunks, raise_at=1, raise_exc=requests.exceptions.ReadTimeout("slow"))
        monkeypatch.setattr("app.services.llm.ollama.requests.post", lambda *a, **k: resp)

        fired = []
        lines = list(_pull_llm().pull_model("qwen2.5:3b", on_success=lambda: fired.append(1)))

        assert any("error" in json.loads(line) for line in lines)
        assert not any(json.loads(line).get("status") == "success" for line in lines)
        assert fired == []

    @pytest.mark.parametrize("exc", [
        requests.exceptions.ChunkedEncodingError("connection broken"),
        requests.exceptions.ConnectionError("connection reset"),
    ])
    def test_connection_lost_mid_stream_yields_error_no_success(self, monkeypatch, exc):
        """ChunkedEncodingError or ConnectionError mid-stream: error line, no success, no callback."""
        import json

        chunks = [b'{"status": "downloading"}\n', b"partial"]
        resp = _FakeStreamResponse(chunks, raise_at=1, raise_exc=exc)
        monkeypatch.setattr("app.services.llm.ollama.requests.post", lambda *a, **k: resp)

        fired = []
        lines = list(_pull_llm().pull_model("qwen2.5:3b", on_success=lambda: fired.append(1)))

        errors = [json.loads(line) for line in lines if "error" in json.loads(line)]
        assert errors
        assert errors[0]["error"]
        assert not any(json.loads(line).get("status") == "success" for line in lines)
        assert fired == []

    def test_ollama_down_before_stream_raises_unavailable(self, monkeypatch):
        """ConnectionError before any data → LLMUnavailableError (HTTP 503)."""
        monkeypatch.setattr(
            "app.services.llm.ollama.requests.post",
            lambda *a, **k: (_ for _ in ()).throw(requests.exceptions.ConnectionError("down")),
        )
        with pytest.raises(LLMUnavailableError, match="Could not reach Ollama"):
            _pull_llm().pull_model("qwen2.5:3b")

    def test_connect_timeout_before_stream_raises_unavailable(self, monkeypatch):
        """Timeout before receiving any data → LLMUnavailableError."""
        monkeypatch.setattr(
            "app.services.llm.ollama.requests.post",
            lambda *a, **k: (_ for _ in ()).throw(requests.exceptions.Timeout("timeout")),
        )
        with pytest.raises(LLMUnavailableError):
            _pull_llm().pull_model("qwen2.5:3b")

    def test_uses_correct_timeout_and_body(self, monkeypatch):
        """requests.post receives timeout=(10, pull_timeout) and body with model name."""
        calls = []

        def fake_post(url, **kwargs):
            calls.append(kwargs)
            return _FakeStreamResponse([b'{"status": "success"}\n'])

        monkeypatch.setattr("app.services.llm.ollama.requests.post", fake_post)
        list(_pull_llm(pull_timeout=77).pull_model("llama3.2:3b"))

        assert calls[0]["timeout"] == (10, 77)
        assert calls[0]["json"] == {"model": "llama3.2:3b", "stream": True}
        assert calls[0]["stream"] is True

    def test_json_line_split_across_chunks(self, monkeypatch):
        """A JSON line split over two chunks is reassembled correctly."""
        import json

        half1 = b'{"status": "pull'
        half2 = b'ing manifest"}\n{"status": "success"}\n'
        resp = _FakeStreamResponse([half1, half2])
        monkeypatch.setattr("app.services.llm.ollama.requests.post", lambda *a, **k: resp)

        lines = list(_pull_llm().pull_model("qwen2.5:3b"))
        parsed = [json.loads(line) for line in lines]
        statuses = [p["status"] for p in parsed]
        assert "pulling manifest" in statuses
        assert "success" in statuses

    def test_empty_lines_and_utf8_content(self, monkeypatch):
        """Empty lines are skipped; UTF-8 bytes are decoded."""
        import json

        chunks = [
            b"\n",
            b'{"status": "verifying checksum"}\n',
            b"\n\n",
            b'{"status": "success"}\n',
        ]
        resp = _FakeStreamResponse(chunks)
        monkeypatch.setattr("app.services.llm.ollama.requests.post", lambda *a, **k: resp)

        lines = list(_pull_llm().pull_model("qwen2.5:3b"))
        # No empty lines yielded
        assert all(line.strip() for line in lines)
        parsed = [json.loads(line) for line in lines]
        assert parsed[-1]["status"] == "success"

    def test_no_success_event_returns_error_without_callback(self, monkeypatch):
        """A clean EOF without a success event is an error, not an implicit success."""
        import json

        chunks = [b'{"status": "pulling manifest"}\n']
        resp = _FakeStreamResponse(chunks)
        monkeypatch.setattr("app.services.llm.ollama.requests.post", lambda *a, **k: resp)

        fired = []
        lines = list(_pull_llm().pull_model("qwen2.5:3b", on_success=lambda: fired.append(1)))

        parsed = [json.loads(line) for line in lines]
        assert parsed[-1] == {"error": "Ollama closed the stream before reporting success"}
        assert not any(event.get("status") == "success" for event in parsed)
        assert fired == []

    def test_ollama_success_is_forwarded_once_after_callback(self, monkeypatch):
        """Duplicate Ollama success events produce one line after the callback."""
        import json

        chunks = [
            b'{"status": "pulling manifest"}\n',
            b'{"status": "success"}\n',
            b'{"status": "success"}\n',
        ]
        resp = _FakeStreamResponse(chunks)
        monkeypatch.setattr("app.services.llm.ollama.requests.post", lambda *a, **k: resp)

        events = []
        lines = []

        def on_success():
            events.append("callback")

        for line in _pull_llm().pull_model("qwen2.5:3b", on_success=on_success):
            lines.append(line)
            if json.loads(line).get("status") == "success":
                events.append("success")

        parsed = [json.loads(line) for line in lines]
        assert [event for event in parsed if event.get("status") == "success"] == [{"status": "success"}]
        assert events == ["callback", "success"]


# ---------------------------------------------------------------------------
# load_settings: Ollama pull_timeout and installable_models
# ---------------------------------------------------------------------------

class TestLLMSecretKey:

    def _configure_file(self, monkeypatch, path):
        from app.core import config
        from app.services.llm import user_config

        monkeypatch.setattr(config, "LLM_SECRET_KEY", "")
        monkeypatch.setattr(config, "LLM_SECRET_KEY_FILE", path)
        user_config._invalid_credentials.clear()
        user_config._warned_credential_errors.clear()

    def test_api_generates_key_file_on_first_credential_save(self, tmp_path, monkeypatch):
        from app.services.llm.user_config import decrypt_api_key, encrypt_api_key

        key_file = tmp_path / "secrets" / "llm_secret.key"
        self._configure_file(monkeypatch, key_file)

        assert not key_file.exists()
        encrypted = encrypt_api_key("provider-secret")

        assert key_file.is_file()
        assert decrypt_api_key(encrypted, "openai") == "provider-secret"
        if os.name == "posix":
            assert stat.S_IMODE(key_file.stat().st_mode) == 0o600

    def test_key_file_is_reused_by_a_separate_process(self, tmp_path, monkeypatch):
        from app.services.llm.user_config import encrypt_api_key

        key_file = tmp_path / "secrets" / "llm_secret.key"
        self._configure_file(monkeypatch, key_file)
        encrypted = encrypt_api_key("provider-secret")

        env = os.environ.copy()
        env["LLM_SECRET_KEY"] = ""
        env["LLM_SECRET_KEY_FILE"] = str(key_file)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from app.services.llm.user_config import decrypt_api_key; "
                f"print(decrypt_api_key({encrypted!r}, 'openai') or '')",
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.stdout.strip() == "provider-secret"

    def test_worker_process_sees_provider_credential_saved_in_database(self, tmp_path, monkeypatch):
        from sqlmodel import Session, SQLModel, create_engine

        from app.core import config
        from app.models import LLMProviderCredential
        from app.services.llm.user_config import encrypt_api_key

        database_path = tmp_path / "worker-state.sqlite"
        database_url = f"sqlite:///{database_path.as_posix()}"
        engine = create_engine(database_url)
        SQLModel.metadata.create_all(engine)
        secret_key = Fernet.generate_key().decode("ascii")
        monkeypatch.setattr(config, "LLM_SECRET_KEY", secret_key)
        monkeypatch.setattr(config, "LLM_SECRET_KEY_FILE", tmp_path / "unused.key")
        encrypted = encrypt_api_key("worker-provider-secret")
        with Session(engine) as session:
            session.add(
                LLMProviderCredential(
                    provider="openai",
                    api_key_encrypted=encrypted,
                    key_hint="cret",
                )
            )
            session.commit()

        env = os.environ.copy()
        env.update({
            "DATABASE_URL": database_url,
            "LLM_SECRET_KEY": secret_key,
            "LLM_PROVIDER": "ollama",
            "LLM_ALLOW_EXTERNAL": "true",
            "OLLAMA_HOST": "http://localhost:11434",
            "OLLAMA_MODELS": "*",
            "OPENAI_MODELS": "",
            "OPENAI_API_KEY": "",
        })
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from sqlmodel import Session, create_engine; "
                "from app.services.llm.user_config import effective_registry; "
                "engine = create_engine(__import__('os').environ['DATABASE_URL']); "
                "session = Session(engine); "
                "print(','.join(p.value for p in effective_registry(session).providers)); "
                "session.close()",
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

        assert "openai" in result.stdout.strip().split(",")
        assert "worker-provider-secret" not in result.stdout + result.stderr

    def test_environment_key_overrides_existing_key_file(self, tmp_path, monkeypatch):
        from app.core import config
        from app.services.llm.user_config import decrypt_api_key, encrypt_api_key

        key_file = tmp_path / "existing.key"
        file_key = Fernet.generate_key()
        key_file.write_bytes(file_key)
        monkeypatch.setattr(config, "LLM_SECRET_KEY", Fernet.generate_key().decode("ascii"))
        monkeypatch.setattr(config, "LLM_SECRET_KEY_FILE", key_file)

        encrypted = encrypt_api_key("provider-secret")

        assert decrypt_api_key(encrypted, "openai") == "provider-secret"
        assert key_file.read_bytes() == file_key

    def test_missing_file_is_warning_for_reader_and_not_created(self, tmp_path, monkeypatch, caplog):
        from app.services.llm.user_config import decrypt_api_key

        key_file = tmp_path / "missing.key"
        self._configure_file(monkeypatch, key_file)

        assert decrypt_api_key("not-a-valid-token", "openai") is None
        assert not key_file.exists()
        assert "cannot be decrypted" in caplog.text

    def test_corrupt_file_is_warning_for_reader_and_cannot_be_overwritten(self, tmp_path, monkeypatch, caplog):
        from app.services.llm.user_config import decrypt_api_key, encrypt_api_key

        key_file = tmp_path / "corrupt.key"
        key_file.write_text("not-a-fernet-key", encoding="ascii")
        self._configure_file(monkeypatch, key_file)

        assert decrypt_api_key("not-a-valid-token", "openai") is None
        assert "cannot be decrypted" in caplog.text
        with pytest.raises(LLMSecretKeyError, match="master key is unavailable"):
            encrypt_api_key("provider-secret")
        assert key_file.read_text(encoding="ascii") == "not-a-fernet-key"

    def test_unreadable_default_credential_falls_back_to_ollama(self, tmp_path, monkeypatch, caplog):
        from copy import deepcopy

        from app.api.schemas.enums import LLMProvider
        from app.core import config
        from app.models import LLMProviderCredential
        from app.services.llm.user_config import _build_registry, decrypt_api_key

        self._configure_file(monkeypatch, tmp_path / "missing.key")
        monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
        monkeypatch.setattr(config, "LLM_MODEL", "")
        provider_env = deepcopy(config.LLM_PROVIDER_ENV)
        provider_env["openai"]["MODELS"] = ""
        provider_env["openai"]["API_KEY"] = ""
        monkeypatch.setattr(config, "LLM_PROVIDER_ENV", provider_env)

        registry = _build_registry(
            {"openai": LLMProviderCredential(provider="openai", api_key_encrypted="saved-ciphertext")},
            [],
            False,
        )

        assert registry.default.provider is LLMProvider.ollama
        assert decrypt_api_key("saved-ciphertext", "openai") is None
        assert sum("cannot be decrypted" in record.getMessage() for record in caplog.records) == 1

    def test_environment_only_registry_remains_the_default(self, monkeypatch, test_registry):
        from app.services.llm import user_config

        class EmptySession:
            reads = 0

            def exec(self, _statement):
                self.reads += 1
                return SimpleNamespace(all=lambda: [])

            def get(self, _model, _key):
                return None

        session = EmptySession()
        monkeypatch.setattr(user_config.time, "monotonic", lambda: 100.0)
        user_config.invalidate_registry_cache()
        try:
            assert user_config.effective_registry(session) is test_registry
            assert user_config.effective_registry(session) is test_registry
            assert session.reads == 2
        finally:
            user_config.invalidate_registry_cache()

    def test_effective_registry_checks_database_only_every_few_seconds(self, monkeypatch, test_registry):
        from datetime import datetime, timezone
        from types import SimpleNamespace

        from app.services.llm import user_config

        now = [100.0]
        credential = SimpleNamespace(
            provider="gemini",
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            key_hint=None,
            base_url=None,
            structured_output=None,
            api_key_encrypted=None,
        )

        class FakeSession:
            def __init__(self):
                self.reads = 0

            def exec(self, _statement):
                records = [credential] if self.reads % 2 == 0 else []
                self.reads += 1
                return SimpleNamespace(all=lambda: records)

            def get(self, _model, _key):
                return None

        session = FakeSession()
        builds = []
        monkeypatch.setattr(user_config.time, "monotonic", lambda: now[0])
        monkeypatch.setattr(
            user_config,
            "_build_registry",
            lambda *_args, **_kwargs: builds.append(1) or test_registry,
        )
        user_config.invalidate_registry_cache()

        try:
            assert user_config.effective_registry(session) is test_registry
            assert user_config.effective_registry(session) is test_registry
            assert session.reads == 2
            assert len(builds) == 1

            now[0] += user_config._REGISTRY_CHECK_SECONDS + 0.1
            user_config.effective_registry(session)
            assert session.reads == 4
            assert len(builds) == 1

            credential.updated_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
            now[0] += user_config._REGISTRY_CHECK_SECONDS + 0.1
            user_config.effective_registry(session)
            assert session.reads == 6
            assert len(builds) == 2
        finally:
            user_config.invalidate_registry_cache()


# ---------------------------------------------------------------------------
# load_settings: Ollama pull_timeout and installable_models
# ---------------------------------------------------------------------------

class TestOllamaSettings:

    def _ollama_cfg(self, **overrides):
        base = {
            "OLLAMA_MODEL": "qwen2.5:1.5b",
            "OLLAMA_TIMEOUT": 300,
            "OLLAMA_PULL_TIMEOUT": 120,
            "OLLAMA_INSTALLABLE_MODELS": "",
            "LLM_PROVIDER": "ollama",
            "LLM_MODEL": "",
            "LLM_TIMEOUT": "",
            "LLM_MAX_RETRIES": "",
            "LLM_ALLOW_EXTERNAL": "false",
            "LLM_TEMPERATURE": "0",
            "LLM_PROVIDER_ENV": {"ollama": {"BASE_URL": "http://ollama:11434", "MODELS": "*"}},
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_default_pull_timeout(self):
        settings = load_settings(self._ollama_cfg())
        assert settings.providers[LLMProvider.ollama].pull_timeout == 120

    def test_custom_pull_timeout(self):
        settings = load_settings(self._ollama_cfg(OLLAMA_PULL_TIMEOUT=60))
        assert settings.providers[LLMProvider.ollama].pull_timeout == 60

    def test_invalid_pull_timeout_names_setting(self):
        with pytest.raises(LLMConfigError, match="OLLAMA_PULL_TIMEOUT"):
            load_settings(self._ollama_cfg(OLLAMA_PULL_TIMEOUT="fast"))

    def test_empty_installable_uses_default_list(self):
        from app.services.llm.specs import DEFAULT_OLLAMA_INSTALLABLE_MODELS
        settings = load_settings(self._ollama_cfg(OLLAMA_INSTALLABLE_MODELS=""))
        assert settings.providers[LLMProvider.ollama].installable_models == DEFAULT_OLLAMA_INSTALLABLE_MODELS

    def test_explicit_installable_models_parsed(self):
        settings = load_settings(self._ollama_cfg(OLLAMA_INSTALLABLE_MODELS="llama3.2:3b, qwen2.5:7b"))
        assert settings.providers[LLMProvider.ollama].installable_models == ("llama3.2:3b", "qwen2.5:7b")

    def test_installable_models_deduplication(self):
        settings = load_settings(self._ollama_cfg(OLLAMA_INSTALLABLE_MODELS="a:1b,a:1b,b:2b"))
        assert settings.providers[LLMProvider.ollama].installable_models == ("a:1b", "b:2b")

    def test_create_llm_passes_pull_timeout(self):
        settings = load_settings(self._ollama_cfg(OLLAMA_PULL_TIMEOUT=45))
        llm = create_llm(settings.providers[LLMProvider.ollama])
        assert isinstance(llm, OllamaLLM)
        assert llm.pull_timeout == 45
