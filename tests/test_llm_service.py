"""Tests for the LLM module.

Nothing here touches a network. The provider table is resolved against a
stand-in config object, and the OpenAI client is replaced with a fake that
records what it was asked for and hands back whatever the test lined up.
"""

from types import SimpleNamespace

import httpx
import openai
import pytest

from app.services.llm import client as llm_client
from app.services.llm import providers
from app.services.llm.errors import (
    LLMAuthError,
    LLMConfigError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.services.llm.gate import RateLimitGate
from app.services.llm.parsing import close_truncated, extract_json_object

DEFAULTS = {
    "LLM_PROVIDER": "ollama",
    "LLM_MODEL": "",
    "LLM_BASE_URL": "",
    "LLM_API_KEY": "",
    "OPENAI_API_KEY": "",
    "GEMINI_API_KEY": "",
    "ANTHROPIC_API_KEY": "",
    "LLM_EXTRA_HEADERS": "",
    "LLM_ALLOW_EXTERNAL": False,
    "LLM_TIMEOUT": 600,
    "LLM_MAX_TOKENS": 1200,
    "LLM_RATE_LIMIT_RETRIES": 10,
    "LLM_RATE_LIMIT_WAIT_SECONDS": 10.0,
    "LLM_RATE_LIMIT_MAX_WAIT_SECONDS": 60.0,
    "LLM_RESPECT_RETRY_AFTER": True,
    "LLM_SERVER_RETRIES": 2,
    "LLM_SERVER_RETRY_WAIT_SECONDS": 2.0,
    "OLLAMA_HOST": "http://ollama:11434",
    "OLLAMA_MODEL": "qwen2.5:1.5b",
}


# ---------------------------------------------------------------------------
# Fixtures and fakes
# ---------------------------------------------------------------------------


@pytest.fixture
def configure(monkeypatch):
    """Point the module at a stand-in config, and clear its caches after."""

    def _configure(**overrides):
        cfg = SimpleNamespace(**{**DEFAULTS, **overrides})
        monkeypatch.setattr(providers, "app_config", cfg)
        llm_client.reset()
        return cfg

    yield _configure
    llm_client.reset()


@pytest.fixture
def no_sleep(monkeypatch):
    """Record the waits instead of serving them."""
    waits: list[float] = []
    monkeypatch.setattr(llm_client.time, "sleep", waits.append)
    return waits


def answer(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


class FakeCompletions:
    def __init__(self, results):
        self.results = list(results)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, Exception):
            raise result
        return result


def install(monkeypatch, results, models=None):
    """Replace the SDK client with a fake, and hand back the completions stub."""
    completions = FakeCompletions(results)

    def list_models():
        if isinstance(models, Exception):
            raise models
        return [SimpleNamespace(id=name) for name in (models or [])]

    fake = SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
        models=SimpleNamespace(list=list_models),
    )
    monkeypatch.setattr(llm_client, "_client", fake)
    return completions


def http_error(kind, status, headers=None, message=None):
    request = httpx.Request("POST", "http://provider/v1/chat/completions")
    response = httpx.Response(status, headers=headers or {}, request=request)
    return kind(message or f"{status} from the provider", response=response, body=None)


# ---------------------------------------------------------------------------
# Provider table and configuration
# ---------------------------------------------------------------------------


class TestResolve:
    def test_ollama_is_the_default_and_needs_nothing(self, configure):
        settings = providers.resolve(configure())
        assert settings.provider == "ollama"
        assert settings.model == "qwen2.5:1.5b"
        assert settings.base_url == "http://ollama:11434/v1"
        assert settings.external is False
        assert settings.json_mode is True

    def test_unknown_provider_names_the_valid_ones(self, configure):
        with pytest.raises(LLMConfigError) as exc:
            providers.resolve(configure(LLM_PROVIDER="llamafile"))
        assert "llamafile" in str(exc.value)
        assert "ollama" in str(exc.value)

    def test_hosted_provider_needs_its_key(self, configure):
        with pytest.raises(LLMConfigError, match="OPENAI_API_KEY"):
            providers.resolve(
                configure(
                    LLM_PROVIDER="openai",
                    LLM_MODEL="gpt-4o-mini",
                    LLM_ALLOW_EXTERNAL=True,
                )
            )

    def test_hosted_provider_needs_a_model_named(self, configure):
        with pytest.raises(LLMConfigError, match="LLM_MODEL"):
            providers.resolve(
                configure(
                    LLM_PROVIDER="gemini",
                    GEMINI_API_KEY="k",
                    LLM_ALLOW_EXTERNAL=True,
                )
            )

    def test_hosted_provider_blocked_without_the_external_flag(self, configure):
        with pytest.raises(LLMConfigError, match="LLM_ALLOW_EXTERNAL"):
            providers.resolve(
                configure(LLM_PROVIDER="openai", LLM_MODEL="gpt-4o-mini", OPENAI_API_KEY="k")
            )

    def test_hosted_provider_allowed_once_the_flag_is_set(self, configure):
        settings = providers.resolve(
            configure(
                LLM_PROVIDER="openai",
                LLM_MODEL="gpt-4o-mini",
                OPENAI_API_KEY="k",
                LLM_ALLOW_EXTERNAL=True,
            )
        )
        assert settings.external is True
        assert settings.base_url is None  # the SDK's own default

    def test_anthropic_has_no_json_mode_so_it_prefills(self, configure):
        settings = providers.resolve(
            configure(
                LLM_PROVIDER="anthropic",
                LLM_MODEL="claude-sonnet-4-6",
                ANTHROPIC_API_KEY="k",
                LLM_ALLOW_EXTERNAL=True,
            )
        )
        assert settings.json_mode is False
        assert settings.json_prefill is True

    def test_custom_endpoint_needs_a_base_url(self, configure):
        with pytest.raises(LLMConfigError, match="LLM_BASE_URL"):
            providers.resolve(configure(LLM_PROVIDER="custom", LLM_MODEL="mistral"))

    def test_custom_endpoint_on_this_machine_is_not_external(self, configure):
        settings = providers.resolve(
            configure(
                LLM_PROVIDER="custom",
                LLM_MODEL="mistral",
                LLM_BASE_URL="http://localhost:8001/v1",
            )
        )
        assert settings.external is False
        assert settings.api_key == providers._NO_KEY_PLACEHOLDER

    @pytest.mark.parametrize(
        "url", ["http://192.168.1.9:8001/v1", "http://10.0.0.4/v1", "http://vllm:8000/v1"]
    )
    def test_custom_endpoint_on_the_local_network_is_not_external(self, configure, url):
        settings = providers.resolve(
            configure(LLM_PROVIDER="custom", LLM_MODEL="m", LLM_BASE_URL=url)
        )
        assert settings.external is False

    def test_custom_endpoint_off_site_still_needs_the_flag(self, configure):
        with pytest.raises(LLMConfigError, match="LLM_ALLOW_EXTERNAL"):
            providers.resolve(
                configure(
                    LLM_PROVIDER="custom",
                    LLM_MODEL="mixtral",
                    LLM_BASE_URL="https://openrouter.ai/api/v1",
                )
            )

    def test_base_url_override_wins_for_a_named_provider(self, configure):
        settings = providers.resolve(
            configure(LLM_PROVIDER="ollama", LLM_BASE_URL="http://gpu-box:11434/v1")
        )
        assert settings.base_url == "http://gpu-box:11434/v1"

    def test_extra_headers_must_be_a_json_object(self, configure):
        with pytest.raises(LLMConfigError, match="LLM_EXTRA_HEADERS"):
            providers.resolve(configure(LLM_EXTRA_HEADERS="not json"))

    def test_extra_headers_are_parsed(self, configure):
        settings = providers.resolve(configure(LLM_EXTRA_HEADERS='{"X-Tenant": "fire-dept"}'))
        assert settings.extra_headers == {"X-Tenant": "fire-dept"}

    def test_nonsense_limits_are_refused(self, configure):
        with pytest.raises(LLMConfigError, match="greater than zero"):
            providers.resolve(configure(LLM_MAX_TOKENS=0))


# ---------------------------------------------------------------------------
# Building the request
# ---------------------------------------------------------------------------


class TestRequestShape:
    def test_json_mode_is_asked_for_where_it_works(self, configure, monkeypatch):
        configure()
        calls = install(monkeypatch, [answer('{"a": 1}')])
        llm_client.generate_json("find things")

        sent = calls.calls[0]
        assert sent["response_format"] == {"type": "json_object"}
        assert sent["temperature"] == 0
        assert sent["max_tokens"] == 1200
        assert sent["model"] == "qwen2.5:1.5b"
        assert sent["messages"] == [{"role": "user", "content": "find things"}]

    def test_anthropic_gets_a_prefill_instead_of_json_mode(self, configure, monkeypatch):
        configure(
            LLM_PROVIDER="anthropic",
            LLM_MODEL="claude-sonnet-4-6",
            ANTHROPIC_API_KEY="k",
            LLM_ALLOW_EXTERNAL=True,
        )
        calls = install(monkeypatch, [answer('"a": 1}')])
        result = llm_client.generate_json("find things")

        sent = calls.calls[0]
        assert "response_format" not in sent
        assert sent["messages"][-1] == {"role": "assistant", "content": "{"}
        # The opening brace the model continued from is put back before parsing.
        assert result == {"a": 1}

    def test_a_model_named_by_the_caller_wins(self, configure, monkeypatch):
        configure()
        calls = install(monkeypatch, [answer("hello")])
        llm_client.generate("hi", model="llama3.2")
        assert calls.calls[0]["model"] == "llama3.2"

    def test_a_refused_parameter_is_dropped_and_the_call_retried(self, configure, monkeypatch):
        configure()
        refusal = http_error(
            openai.BadRequestError,
            400,
            message="Unsupported parameter: 'temperature' is not supported with this model",
        )
        calls = install(monkeypatch, [refusal, answer("fine")])

        assert llm_client.generate("hi") == "fine"
        assert "temperature" not in calls.calls[1]


# ---------------------------------------------------------------------------
# Rate limits
# ---------------------------------------------------------------------------


class TestRateLimits:
    def test_a_429_is_retried_ten_times_then_gives_up(self, configure, monkeypatch, no_sleep):
        configure()
        limited = http_error(openai.RateLimitError, 429)
        calls = install(monkeypatch, [limited])

        with pytest.raises(LLMRateLimitError) as exc:
            llm_client.generate("hi")

        assert len(calls.calls) == 11  # the first try plus ten retries
        assert no_sleep == [10.0] * 10
        assert exc.value.retry_after_seconds == 10.0

    def test_it_recovers_when_the_limit_lifts(self, configure, monkeypatch, no_sleep):
        configure()
        limited = http_error(openai.RateLimitError, 429)
        calls = install(monkeypatch, [limited, limited, answer("done")])

        assert llm_client.generate("hi") == "done"
        assert len(calls.calls) == 3
        assert no_sleep == [10.0, 10.0]

    def test_a_longer_retry_after_is_honoured(self, configure, monkeypatch, no_sleep):
        configure()
        limited = http_error(openai.RateLimitError, 429, headers={"retry-after": "25"})
        install(monkeypatch, [limited, answer("done")])

        llm_client.generate("hi")
        assert no_sleep == [25.0]

    def test_an_unreasonable_retry_after_is_capped(self, configure, monkeypatch, no_sleep):
        configure()
        limited = http_error(openai.RateLimitError, 429, headers={"retry-after": "3600"})
        install(monkeypatch, [limited, answer("done")])

        llm_client.generate("hi")
        assert no_sleep == [60.0]

    def test_a_shorter_retry_after_does_not_shorten_the_wait(
        self, configure, monkeypatch, no_sleep
    ):
        configure()
        limited = http_error(openai.RateLimitError, 429, headers={"retry-after": "1"})
        install(monkeypatch, [limited, answer("done")])

        llm_client.generate("hi")
        assert no_sleep == [10.0]

    def test_overloaded_is_treated_like_a_rate_limit(self, configure, monkeypatch, no_sleep):
        configure()
        overloaded = http_error(openai.APIStatusError, 529)
        install(monkeypatch, [overloaded, answer("done")])

        assert llm_client.generate("hi") == "done"
        assert no_sleep == [10.0]


class TestGate:
    def test_the_gate_stops_the_rest_of_the_batch(self, configure, monkeypatch, no_sleep):
        configure()
        limited = http_error(openai.RateLimitError, 429)
        calls = install(monkeypatch, [limited])
        gate = RateLimitGate()

        with pytest.raises(LLMRateLimitError):
            llm_client.generate("first", gate=gate)
        assert gate.tripped
        first_round = len(calls.calls)

        with pytest.raises(LLMRateLimitError, match="rate limiting this run"):
            llm_client.generate("second", gate=gate)

        # The second prompt did not wait, and did not call the provider again.
        assert len(calls.calls) == first_round
        assert no_sleep == [10.0] * 10

    def test_an_untripped_gate_changes_nothing(self, configure, monkeypatch):
        configure()
        install(monkeypatch, [answer("fine")])
        assert llm_client.generate("hi", gate=RateLimitGate()) == "fine"


# ---------------------------------------------------------------------------
# Other failures
# ---------------------------------------------------------------------------


class TestFailures:
    def test_a_rejected_key_is_not_retried(self, configure, monkeypatch, no_sleep):
        configure()
        calls = install(monkeypatch, [http_error(openai.AuthenticationError, 401)])

        with pytest.raises(LLMAuthError, match="rejected the API key"):
            llm_client.generate("hi")
        assert len(calls.calls) == 1
        assert no_sleep == []

    def test_an_unreachable_provider_says_so(self, configure, monkeypatch):
        configure()
        request = httpx.Request("POST", "http://ollama:11434/v1/chat/completions")
        install(monkeypatch, [openai.APIConnectionError(request=request)])

        with pytest.raises(LLMUnavailableError, match="could not reach"):
            llm_client.generate("hi")

    def test_a_timeout_is_reported_as_one(self, configure, monkeypatch):
        configure()
        request = httpx.Request("POST", "http://ollama:11434/v1/chat/completions")
        install(monkeypatch, [openai.APITimeoutError(request=request)])

        with pytest.raises(LLMTimeoutError, match="600s"):
            llm_client.generate("hi")

    def test_a_server_error_is_retried_twice_then_reported(
        self, configure, monkeypatch, no_sleep
    ):
        configure()
        calls = install(monkeypatch, [http_error(openai.APIStatusError, 502)])

        with pytest.raises(LLMUnavailableError, match="502"):
            llm_client.generate("hi")
        assert len(calls.calls) == 3  # the first try plus two retries
        assert no_sleep == [2.0, 2.0]

    def test_an_empty_answer_is_a_response_error(self, configure, monkeypatch):
        configure()
        install(monkeypatch, [SimpleNamespace(choices=[])])

        with pytest.raises(LLMResponseError, match="no answer"):
            llm_client.generate("hi")


# ---------------------------------------------------------------------------
# Parsing what came back
# ---------------------------------------------------------------------------


class TestParsing:
    def test_a_fenced_answer_still_parses(self):
        assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}

    def test_prose_around_the_object_is_ignored(self):
        assert extract_json_object('Sure, here you go: {"a": 1} Hope that helps.') == {"a": 1}

    def test_an_answer_cut_off_keeps_the_complete_fields(self):
        parsed = extract_json_object('{"a": 1, "b": 2, "c": "half a val')
        assert parsed == {"a": 1, "b": 2}

    def test_an_answer_with_no_object_is_rejected(self):
        with pytest.raises(LLMResponseError, match="no JSON object"):
            extract_json_object("I could not find anything.")

    def test_a_list_is_not_an_object(self):
        with pytest.raises(LLMResponseError, match="expected a JSON object"):
            extract_json_object("[1, 2, 3]")


class TestTruncationRepair:
    """The repair pass is only reached once normal parsing has failed.

    What matters is that it never invents a value, only ever drops the field it
    could not see the end of. These pin that.
    """

    @pytest.mark.parametrize(
        "cut, expected",
        [
            ('{"a": 1, "b": 2, "c": "half a val', {"a": 1, "b": 2}),
            ('{"a": 1, "bcd', {"a": 1}),
            ('{"a": 1,', {"a": 1}),
            ('{"a": 1, "b": 12', {"a": 1}),
            ('{"a": {"b": 1}, "c": tru', {"a": {"b": 1}}),
            ('{"a": [1, 2', {"a": [1]}),
            ('{"a": [{"b": 1}, {"c": ', {"a": [{"b": 1}]}),
            ('{"a": "x", "b": "y', {"a": "x"}),
        ],
    )
    def test_complete_fields_survive_and_the_cut_one_is_dropped(self, cut, expected):
        assert extract_json_object(cut) == expected

    def test_a_comma_inside_a_value_is_not_a_field_boundary(self):
        parsed = extract_json_object('{"address": "400 Oak Street, Apt 2", "time": "14:0')
        assert parsed == {"address": "400 Oak Street, Apt 2"}

    def test_a_brace_inside_a_value_is_not_structure(self):
        parsed = extract_json_object('{"note": "he said {this}", "next": "cut')
        assert parsed == {"note": "he said {this}"}

    def test_an_escaped_quote_does_not_end_the_string(self):
        parsed = extract_json_object('{"note": "he said \\"go\\", loudly", "next": "cut')
        assert parsed == {"note": 'he said "go", loudly'}

    def test_a_real_answer_that_hit_the_token_ceiling(self):
        """Verbatim shape of a qwen2.5 answer that ran out of tokens."""
        truncated = (
            '{\n  "incident": {\n    "name": "Oak Street fire",\n'
            '    "alarm_datetime": "2026-04-18T21:14:00-07:00",\n'
            '    "cleared_datetime": "2026-04-18T21:19'
        )
        parsed = extract_json_object(truncated)
        assert parsed["incident"]["name"] == "Oak Street fire"
        assert parsed["incident"]["alarm_datetime"] == "2026-04-18T21:14:00-07:00"
        assert "cleared_datetime" not in parsed["incident"]

    def test_a_cut_off_list_keeps_its_complete_entries(self):
        truncated = '{"units": [{"unit_id": "E12"}, {"unit_id": "E13"}, {"unit_id": "E1'
        assert extract_json_object(truncated) == {
            "units": [{"unit_id": "E12"}, {"unit_id": "E13"}]
        }

    def test_a_cut_before_any_complete_field_gives_up(self):
        assert close_truncated('{"a": 1') is None
        with pytest.raises(LLMResponseError):
            extract_json_object('{"a": 1')

    def test_nothing_usable_gives_up_rather_than_guessing(self):
        assert close_truncated("no json here") is None

    def test_a_complete_answer_never_reaches_the_repair(self):
        assert extract_json_object('{"a": 1, "b": [2, 3]}') == {"a": 1, "b": [2, 3]}


# ---------------------------------------------------------------------------
# Inspecting the provider
# ---------------------------------------------------------------------------


class TestInspection:
    def test_models_are_listed_with_the_configured_one_marked(self, configure, monkeypatch):
        configure()
        install(monkeypatch, [answer("x")], models=["qwen2.5:1.5b", "llama3.2"])

        models = llm_client.list_models()
        assert [m.name for m in models] == ["qwen2.5:1.5b", "llama3.2"]
        assert [m.default for m in models] == [True, False]

    def test_a_provider_that_will_not_list_still_reports_the_configured_model(
        self, configure, monkeypatch
    ):
        configure()
        install(monkeypatch, [answer("x")], models=RuntimeError("no permission"))

        models = llm_client.list_models()
        assert [m.name for m in models] == ["qwen2.5:1.5b"]
        assert models[0].default is True

    def test_a_local_provider_is_probed(self, configure, monkeypatch):
        configure()
        install(monkeypatch, [answer("x")], models=["qwen2.5:1.5b"])

        report = llm_client.health()
        assert report.status == "healthy"
        assert report.probed is True
        assert report.external is False

    def test_a_local_provider_that_is_down_is_unhealthy(self, configure, monkeypatch):
        configure()
        install(monkeypatch, [answer("x")], models=RuntimeError("connection refused"))

        report = llm_client.health()
        assert report.status == "unhealthy"
        assert "connection refused" in report.detail

    def test_a_hosted_provider_is_not_probed(self, configure, monkeypatch):
        configure(
            LLM_PROVIDER="openai",
            LLM_MODEL="gpt-4o-mini",
            OPENAI_API_KEY="k",
            LLM_ALLOW_EXTERNAL=True,
        )
        install(monkeypatch, [answer("x")], models=RuntimeError("should not be called"))

        report = llm_client.health()
        assert report.probed is False
        assert report.external is True
        assert report.status == "healthy"

    def test_health_reports_a_broken_configuration_instead_of_raising(self, configure):
        configure(LLM_PROVIDER="nope")
        report = llm_client.health()
        assert report.status == "unhealthy"
        assert "nope" in report.detail

    def test_check_config_returns_the_resolved_settings(self, configure):
        configure()
        assert llm_client.check_config().model == "qwen2.5:1.5b"


class TestStartupGuards:
    """Both processes that serve extractions have to refuse a bad configuration."""

    def test_the_worker_guard_exits_rather_than_raising(self, configure):
        """Celery swallows anything deriving from Exception in a signal handler,
        logs it and carries on, which would leave a worker running that cannot
        serve a single extraction. SystemExit is the only thing that lands.
        """
        from app.core.celery import _check_llm_config

        configure(LLM_PROVIDER="nonsense")
        with pytest.raises(SystemExit):
            _check_llm_config()

    def test_the_worker_guard_passes_a_good_configuration(self, configure):
        from app.core.celery import _check_llm_config

        configure()
        assert _check_llm_config() is None
