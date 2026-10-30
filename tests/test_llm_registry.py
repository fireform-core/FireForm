"""Tests for picking a provider and model: ModelSelection, LLMRegistry,
ModelValidator, and the endpoints on top of them.

The registry tests use FakeLLM, so nothing goes over the network.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests
from sqlmodel import select

from app.api.schemas.enums import InputStatus, InputType
from app.core.config import API_PREFIX
from app.models import Input, LLMManualModel, LLMProviderCredential, LLMRuntimeConfig
from app.services.llm import (
    LLM,
    LLMAuthError,
    LLMNotAvailableError,
    LLMProvider,
    LLMRegistry,
    LLMSettings,
    LLMUnavailableError,
    ModelChoice,
    ModelInfo,
    ModelValidator,
    ProviderSettings,
)
from app.services.llm.registry import CACHE_SECONDS, FAILURE_CACHE_SECONDS
from app.services.llm.openai_compatible import OpenAICompatibleLLM
from app.services.llm.selection import ModelSelection
from app.services.llm.specs import DEFAULT_OLLAMA_INSTALLABLE_MODELS, SPECS

OLLAMA, GEMINI, OPENAI = LLMProvider.ollama, LLMProvider.gemini, LLMProvider.openai


class FakeLLM(LLM):
    def __init__(self, provider, offered=(), down=False, error=None, list_error=None):
        super().__init__(provider, None, 5)
        self.offered = list(offered)
        self.down = down
        self.error = error
        self.list_error = list_error
        self.list_calls = 0
        self.generated = []

    def _generate(self, prompt, schema, model):
        self.generated.append(model)
        if self.error:
            raise self.error
        return '{"ok": true}'

    def list_models(self):
        self.list_calls += 1
        if self.list_error:
            raise self.list_error
        if self.down:
            raise LLMUnavailableError(f"Could not reach {self.provider.value}")
        return [ModelInfo(name=n) for n in self.offered]

    def health(self):
        raise NotImplementedError


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _provider(provider, models, default_model=None, installable_models=()):
    return ProviderSettings(
        spec=SPECS[provider],
        base_url="http://local:1",
        models=ModelSelection.parse(models),
        default_model=default_model,
        installable_models=installable_models,
    )


def _registry(clients, settings=None, warnings=(), clock=None):
    """Ollama is the default with qwen, offering qwen and llama. Gemini allows
    g1 and g2 but only offers g1."""
    settings = settings or {
        OLLAMA: _provider(OLLAMA, "*", "qwen"),
        GEMINI: _provider(GEMINI, "g1,g2", "g1"),
    }
    llm_settings = LLMSettings(providers=settings, default_provider=OLLAMA, warnings=tuple(warnings))
    return LLMRegistry(llm_settings, clients, clock=clock or Clock())


def _openai_listing(ids):
    client = OpenAICompatibleLLM(
        OPENAI,
        "https://api.openai.com/v1",
        "test-key",
        "gpt-4o-mini",
        5,
    )
    client.client = MagicMock()
    client.client.with_options.return_value.models.list.return_value = [
        SimpleNamespace(id=model_id) for model_id in ids
    ]
    return client


@pytest.fixture
def ollama():
    return FakeLLM(OLLAMA, ["qwen", "llama"])


@pytest.fixture
def gemini():
    return FakeLLM(GEMINI, ["g1", "g3"])


@pytest.fixture
def registry(ollama, gemini):
    return _registry({OLLAMA: ollama, GEMINI: gemini})


# ---------------------------------------------------------------------------
# ModelSelection
# ---------------------------------------------------------------------------

class TestModelSelection:

    def test_parse(self):
        assert ModelSelection.parse("").is_empty
        assert ModelSelection.parse(" , ").is_empty
        assert ModelSelection.parse("*").wildcard
        assert ModelSelection.parse("a,*").wildcard
        assert ModelSelection.parse(" a, b ,a").names == ("a", "b")

    def test_allows(self):
        assert ModelSelection.parse("*").allows("anything")
        assert ModelSelection.parse("a,b").allows("b")
        assert not ModelSelection.parse("a,b").allows("c")

    def test_pick_keeps_configured_order_and_reports_missing(self):
        offered = [ModelInfo(name="c", size_gb=1.0), ModelInfo(name="a")]
        kept, missing = ModelSelection.parse("a,b,c").pick(offered)
        assert [m.name for m in kept] == ["a", "c"]
        assert kept[1].size_gb == 1.0
        assert missing == ["b"]

    def test_pick_wildcard_keeps_everything(self):
        offered = [ModelInfo(name="x"), ModelInfo(name="y")]
        assert ModelSelection.parse("*").pick(offered) == (offered, [])


# ---------------------------------------------------------------------------
# LLMRegistry
# ---------------------------------------------------------------------------

class TestResolve:

    def test_nothing_named_is_the_default_without_asking(self, registry, ollama):
        assert registry.resolve() == ModelChoice(OLLAMA, "qwen")
        assert registry.resolve(OLLAMA, "qwen") == ModelChoice(OLLAMA, "qwen")
        assert ollama.list_calls == 0

    def test_provider_alone_gets_its_default_model(self, registry):
        assert registry.resolve("gemini") == ModelChoice(GEMINI, "g1")

    def test_model_alone_goes_to_the_default_provider(self, registry):
        assert registry.resolve(None, "llama") == ModelChoice(OLLAMA, "llama")

    def test_offered_model_is_checked_once_then_cached(self, registry, ollama):
        registry.resolve(OLLAMA, "llama")
        registry.resolve(OLLAMA, "llama")
        assert ollama.list_calls == 1

    def test_cache_expires(self, ollama, gemini):
        clock = Clock()
        registry = _registry({OLLAMA: ollama, GEMINI: gemini}, clock=clock)
        registry.resolve(OLLAMA, "llama")
        clock.now = CACHE_SECONDS + 1
        registry.resolve(OLLAMA, "llama")
        assert ollama.list_calls == 2

    def test_failure_is_cached_for_less_time(self, gemini):
        clock = Clock()
        down = FakeLLM(OLLAMA, down=True)
        registry = _registry({OLLAMA: down, GEMINI: gemini}, clock=clock)
        registry.provider_catalog(OLLAMA)
        clock.now = FAILURE_CACHE_SECONDS + 1
        registry.provider_catalog(OLLAMA)
        assert down.list_calls == 2

    @pytest.mark.parametrize("provider, model, message", [
        ("openai", None, "openai is not enabled"),
        ("mystery", None, "'mystery' is not a provider"),
        ("gemini", "g9", "g9 is not in GEMINI_MODELS"),
        ("gemini", "g2", "gemini does not offer g2"),
        ("ollama", "missing", "ollama does not offer missing"),
    ])
    def test_unavailable_picks_are_422(self, registry, provider, model, message):
        with pytest.raises(LLMNotAvailableError, match=message) as info:
            registry.resolve(provider, model)
        assert info.value.status_code == 422
        assert info.value.error_code == "LLM_NOT_AVAILABLE"

    def test_name_outside_the_list_is_refused_without_asking(self, registry, gemini):
        with pytest.raises(LLMNotAvailableError):
            registry.resolve(GEMINI, "g9")
        assert gemini.list_calls == 0

    def test_manual_model_is_allowed_offered_and_resolvable(self):
        settings = {
            OLLAMA: _provider(OLLAMA, "*", "qwen"),
            GEMINI: ProviderSettings(
                spec=SPECS[GEMINI],
                base_url="http://local:1",
                models=ModelSelection.parse("g1,manual-model"),
                default_model="g1",
                manual_models=("manual-model",),
            ),
        }
        gemini = FakeLLM(GEMINI, ["g1"])
        registry = _registry(
            {OLLAMA: FakeLLM(OLLAMA, ["qwen"]), GEMINI: gemini},
            settings=settings,
        )

        catalog = registry.provider_catalog(GEMINI)
        assert settings[GEMINI].models.allows("manual-model")
        assert catalog.offers("manual-model")
        assert next(model for model in catalog.models if model.name == "manual-model").manual is True
        assert registry.resolve(GEMINI, "manual-model") == ModelChoice(GEMINI, "manual-model")

    def test_openai_filtered_model_is_not_offered_or_resolvable(self):
        openai_client = _openai_listing(["text-embedding-3-small", "gpt-4o-mini"])
        settings = {
            OLLAMA: _provider(OLLAMA, "*", "qwen"),
            OPENAI: _provider(OPENAI, "*", "gpt-4o-mini"),
        }
        registry = _registry(
            {OLLAMA: FakeLLM(OLLAMA, ["qwen"]), OPENAI: openai_client},
            settings=settings,
        )

        catalog = registry.provider_catalog(OPENAI)

        assert [model.name for model in catalog.models] == ["gpt-4o-mini"]
        with pytest.raises(LLMNotAvailableError, match="does not offer text-embedding-3-small"):
            registry.resolve(OPENAI, "text-embedding-3-small")

    def test_manual_model_can_explicitly_restore_filtered_model(self):
        openai_client = _openai_listing(["text-embedding-3-small", "gpt-4o-mini"])
        settings = {
            OLLAMA: _provider(OLLAMA, "*", "qwen"),
            OPENAI: ProviderSettings(
                spec=SPECS[OPENAI],
                base_url="http://local:1",
                models=ModelSelection.parse("*"),
                default_model="gpt-4o-mini",
                manual_models=("text-embedding-3-small",),
            ),
        }
        registry = _registry(
            {OLLAMA: FakeLLM(OLLAMA, ["qwen"]), OPENAI: openai_client},
            settings=settings,
        )

        catalog = registry.provider_catalog(OPENAI)

        assert [model.name for model in catalog.models] == ["gpt-4o-mini", "text-embedding-3-small"]
        assert catalog.models[1].manual is True
        assert registry.resolve(OPENAI, "text-embedding-3-small") == ModelChoice(
            OPENAI, "text-embedding-3-small"
        )

    def test_manual_gemini_model_can_restore_excluded_id(self):
        model = "gemini-3-pro-image-preview"
        settings = {
            OLLAMA: _provider(OLLAMA, "*", "qwen"),
            GEMINI: ProviderSettings(
                spec=SPECS[GEMINI],
                base_url="http://local:1",
                models=ModelSelection.parse(f"g1,{model}"),
                default_model="g1",
                manual_models=(model,),
            ),
        }
        registry = _registry(
            {OLLAMA: FakeLLM(OLLAMA, ["qwen"]), GEMINI: FakeLLM(GEMINI, ["g1"])},
            settings=settings,
        )

        catalog = registry.provider_catalog(GEMINI)

        assert catalog.offers(model)
        assert next(item for item in catalog.models if item.name == model).manual is True
        assert registry.resolve(GEMINI, model) == ModelChoice(GEMINI, model)

    def test_unreachable_provider_is_503(self, ollama):
        registry = _registry({OLLAMA: ollama, GEMINI: FakeLLM(GEMINI, down=True)})
        with pytest.raises(LLMUnavailableError, match="Could not reach gemini") as info:
            registry.resolve(GEMINI, "g1")
        assert info.value.status_code == 503

    def test_rejected_key_stays_an_auth_error(self, ollama):
        broken = FakeLLM(GEMINI, list_error=LLMAuthError("gemini rejected the API key. Check GEMINI_API_KEY."))
        registry = _registry({OLLAMA: ollama, GEMINI: broken})
        with pytest.raises(LLMAuthError) as info:
            registry.resolve(GEMINI, "g1")
        assert info.value.error_code == "LLM_AUTH_FAILED"
        listing = registry.provider_catalog(GEMINI)
        assert (listing.available, listing.error_code) == (False, "LLM_AUTH_FAILED")

    def test_provider_going_down_and_back_is_logged(self, ollama, caplog):
        clock = Clock()
        gemini = FakeLLM(GEMINI, ["g1"])
        registry = _registry({OLLAMA: ollama, GEMINI: gemini}, clock=clock)
        registry.provider_catalog(GEMINI)
        assert caplog.records == []

        gemini.down = True
        registry.provider_catalog(GEMINI, refresh=True)
        gemini.down = False
        registry.provider_catalog(GEMINI, refresh=True)
        assert [r.getMessage() for r in caplog.records] == [
            "LLM provider gemini is unavailable: Could not reach gemini",
            "LLM provider gemini is available again",
        ]

    def test_verify_false_skips_the_provider(self, registry, gemini):
        assert registry.resolve(GEMINI, "g2", verify=False) == ModelChoice(GEMINI, "g2")
        assert gemini.list_calls == 0

    def test_wildcard_provider_without_default_needs_a_model(self, ollama):
        settings = {OLLAMA: _provider(OLLAMA, "*", "qwen"), OPENAI: _provider(OPENAI, "*")}
        registry = _registry({OLLAMA: ollama, OPENAI: FakeLLM(OPENAI, ["o"])}, settings=settings)
        with pytest.raises(LLMNotAvailableError, match="openai has no default model"):
            registry.resolve(OPENAI)
        assert registry.resolve(OPENAI, "o") == ModelChoice(OPENAI, "o")


class TestCatalogAndGenerate:

    def test_catalog(self, ollama):
        registry = _registry({OLLAMA: ollama, GEMINI: FakeLLM(GEMINI, ["g1", "g3"])})
        by_provider = {c.provider: c for c in registry.catalog()}

        assert [m.name for m in by_provider[OLLAMA].models] == ["qwen", "llama"]
        assert by_provider[OLLAMA].default_model == "qwen"
        gemini = by_provider[GEMINI]
        assert gemini.available
        assert [m.name for m in gemini.models] == ["g1"]
        assert gemini.missing == ("g2",)

    def test_unreachable_provider_has_no_models(self, ollama):
        registry = _registry({OLLAMA: ollama, GEMINI: FakeLLM(GEMINI, down=True)})
        gemini = registry.provider_catalog(GEMINI)
        assert not gemini.available
        assert gemini.models == ()
        assert gemini.detail == "Could not reach gemini"

    def test_refresh_asks_again(self, registry, ollama):
        registry.provider_catalog(OLLAMA)
        registry.provider_catalog(OLLAMA, refresh=True)
        assert ollama.list_calls == 2

    def test_generate_json_goes_to_the_picked_provider(self, registry, ollama, gemini):
        assert registry.generate_json("p", {}, "gemini", "g1") == '{"ok": true}'
        assert gemini.generated == ["g1"]
        registry.generate_json("p", {})
        assert ollama.generated == ["qwen"]


class TestDownloadableCatalog:

    def test_wildcard_downloadable_is_default_installable_minus_offered(self, ollama):
        """OLLAMA_MODELS=* → downloadable = default installable set not yet on Ollama."""
        registry = _registry({OLLAMA: ollama})
        cat = registry.provider_catalog(OLLAMA)
        offered = {m.name for m in cat.models}
        expected = [
            name for name in DEFAULT_OLLAMA_INSTALLABLE_MODELS if name not in offered
        ]
        assert [d.name for d in cat.downloadable] == expected
        assert all(d.installed is False for d in cat.downloadable)

    def test_wildcard_respects_ollama_installable_models_override(self, ollama):
        settings = {OLLAMA: _provider(OLLAMA, "*", "qwen", installable_models=("tiny:1b", "other:2b"))}
        registry = _registry({OLLAMA: ollama}, settings=settings)
        cat = registry.provider_catalog(OLLAMA)
        offered = {m.name for m in cat.models}
        assert [d.name for d in cat.downloadable] == [n for n in ("tiny:1b", "other:2b") if n not in offered]

    def test_explicit_models_list_downloadable_is_missing_not_offered(self, ollama):
        settings = {OLLAMA: _provider(OLLAMA, "qwen,llama,missing", "qwen")}
        registry = _registry({OLLAMA: ollama}, settings=settings)
        cat = registry.provider_catalog(OLLAMA)
        assert cat.missing == ("missing",)
        assert [d.name for d in cat.downloadable] == ["missing"]

    def test_non_ollama_has_no_downloadable_or_installed(self, ollama, gemini):
        registry = _registry({OLLAMA: ollama, GEMINI: gemini})
        cat = registry.provider_catalog(GEMINI)
        assert cat.downloadable == ()
        assert all(getattr(m, "installed", None) is None for m in cat.models)

    def test_resolve_rejects_downloadable_only_model(self, ollama):
        """A model listed as downloadable but not installed cannot be used for fills."""
        settings = {OLLAMA: _provider(OLLAMA, "*", "qwen")}
        ollama.offered = ["qwen"]
        registry = _registry({OLLAMA: ollama}, settings=settings)
        with pytest.raises(LLMNotAvailableError, match="ollama does not offer qwen2.5:3b"):
            registry.resolve(OLLAMA, "qwen2.5:3b")


class TestValidatePull:

    def test_non_ollama_provider_rejected(self, registry):
        with pytest.raises(LLMNotAvailableError, match="only supported for Ollama"):
            registry.validate_pull("gemini", "g1")

    def test_ollama_disabled_rejected(self):
        settings = {GEMINI: _provider(GEMINI, "g1", "g1")}
        llm_settings = LLMSettings(providers=settings, default_provider=GEMINI, warnings=())
        registry = LLMRegistry(llm_settings, {GEMINI: FakeLLM(GEMINI, ["g1"])})
        with pytest.raises(LLMNotAvailableError, match="ollama is not enabled"):
            registry.validate_pull("ollama", "qwen2.5:3b")

    def test_wildcard_rejects_model_outside_installable_set(self, ollama):
        registry = _registry({OLLAMA: ollama})
        with pytest.raises(LLMNotAvailableError, match="cannot be pulled"):
            registry.validate_pull("ollama", "secret:model")

    def test_explicit_list_rejects_model_not_in_ollama_models(self, ollama):
        settings = {OLLAMA: _provider(OLLAMA, "qwen,llama", "qwen")}
        registry = _registry({OLLAMA: ollama}, settings=settings)
        with pytest.raises(LLMNotAvailableError, match="is not in OLLAMA_MODELS"):
            registry.validate_pull("ollama", "mistral:7b")

    def test_valid_wildcard_installable_passes(self, ollama):
        registry = _registry({OLLAMA: ollama})
        registry.validate_pull("ollama", "qwen2.5:3b")

    def test_valid_explicit_configured_missing_passes(self, ollama):
        settings = {OLLAMA: _provider(OLLAMA, "qwen,llama", "qwen")}
        registry = _registry({OLLAMA: ollama}, settings=settings)
        registry.validate_pull("ollama", "llama")


# ---------------------------------------------------------------------------
# ModelValidator
# ---------------------------------------------------------------------------

class TestModelValidator:

    def test_check_config(self):
        registry = _registry(
            {OLLAMA: FakeLLM(OLLAMA, ["llama"]), GEMINI: FakeLLM(GEMINI, ["g1"])},
            warnings=["openai is off: OPENAI_API_KEY is needed."],
        )
        assert ModelValidator(registry).check_config() == [
            "openai is off: OPENAI_API_KEY is needed.",
            "ollama does not offer the default model qwen. Fills will fail.",
            "GEMINI_MODELS has g2, but gemini does not offer it. It is left out of the model list.",
        ]

    def test_filtered_default_warns_without_crashing_or_switching_provider(self):
        openai_client = _openai_listing(["text-embedding-3-small", "gpt-4o-mini"])
        settings = {
            OPENAI: _provider(OPENAI, "*", "text-embedding-3-small"),
        }
        registry = LLMRegistry(
            LLMSettings(providers=settings, default_provider=OPENAI),
            {OPENAI: openai_client},
        )

        warnings = ModelValidator(registry).check_config()

        assert warnings == [
            "openai does not offer the default model text-embedding-3-small. Fills will fail."
        ]
        assert registry.resolve() == ModelChoice(OPENAI, "text-embedding-3-small")
        assert registry.default.provider is OPENAI

    def test_check_config_unreachable(self, ollama):
        registry = _registry({OLLAMA: ollama, GEMINI: FakeLLM(GEMINI, down=True)})
        assert ModelValidator(registry).check_config() == [
            "Could not check the gemini models. Could not reach gemini",
        ]

    def test_probe_ok(self, registry, gemini):
        check = ModelValidator(registry).probe("gemini", "g1")
        assert (check.provider, check.model, check.ok, check.detail) == (GEMINI, "g1", True, None)
        assert check.latency_ms is not None
        assert gemini.generated == ["g1"]

    def test_probe_failure_is_a_result(self, ollama):
        broken = FakeLLM(GEMINI, ["g1"], error=LLMUnavailableError("Could not reach gemini"))
        registry = _registry({OLLAMA: ollama, GEMINI: broken})
        check = ModelValidator(registry).probe("gemini", "g2")
        assert not check.ok
        assert check.detail == "Could not reach gemini"
        assert check.error_code == "LLM_UNAVAILABLE"

    def test_probe_refuses_disabled_provider(self, registry):
        with pytest.raises(LLMNotAvailableError):
            ModelValidator(registry).probe("openai", "o")


# ---------------------------------------------------------------------------
# Endpoints. Use the conftest registry: one Ollama listing every model.
# ---------------------------------------------------------------------------

@pytest.fixture
def ollama_offers(test_llm, monkeypatch):
    """Make the conftest Ollama offer these models."""
    def offer(*names):
        monkeypatch.setattr(test_llm, "list_models", lambda: [ModelInfo(name=n) for n in names])
    return offer


class TestLLMEndpoints:

    def test_save_status_and_delete_credential_never_return_key(self, client, db, monkeypatch, tmp_path):
        from cryptography.fernet import Fernet

        from app.core import config
        from app.services.llm import user_config

        secret = "custom-provider-secret-value"
        monkeypatch.setattr(config, "LLM_SECRET_KEY", Fernet.generate_key().decode("ascii"))
        monkeypatch.setattr(config, "LLM_SECRET_KEY_FILE", tmp_path / "unused.key")
        db.add(LLMRuntimeConfig(id=1, allow_external=True))
        db.commit()
        user_config.invalidate_registry_cache()
        try:
            saved = client.put(
                f"{API_PREFIX}/system/llm/providers/config/custom",
                json={"api_key": secret, "base_url": "http://vllm:8000/v1"},
            )
            assert saved.status_code == 200
            assert secret not in saved.text
            assert saved.json()["source"] == "ui"

            status = client.get(f"{API_PREFIX}/system/llm/providers/config")
            assert status.status_code == 200
            assert secret not in status.text

            deleted = client.delete(f"{API_PREFIX}/system/llm/providers/config/custom")
            assert deleted.status_code == 200
            assert db.exec(select(LLMProviderCredential)).all() == []
            assert db.exec(select(LLMManualModel)).all() == []
        finally:
            user_config.invalidate_registry_cache()

    def test_validate_provider_candidate_does_not_save_configuration(self, client, db, monkeypatch):
        from app.api.routes import llm_config

        custom = LLMProvider.custom
        settings = {
            OLLAMA: _provider(OLLAMA, "*", "qwen"),
            custom: ProviderSettings(
                spec=SPECS[custom],
                base_url="http://vllm:8000/v1",
                models=ModelSelection.parse("model-a"),
                default_model="model-a",
            ),
        }
        candidate = _registry(
            {OLLAMA: FakeLLM(OLLAMA, ["qwen"]), custom: FakeLLM(custom, ["model-a"])},
            settings=settings,
        )
        monkeypatch.setattr(llm_config, "registry_for_candidate", lambda *_args, **_kwargs: candidate)

        response = client.post(
            f"{API_PREFIX}/system/llm/providers/config/custom/validate",
            json={"base_url": "http://vllm:8000/v1"},
        )

        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert [model["name"] for model in response.json()["models"]] == ["model-a"]
        assert db.exec(select(LLMProviderCredential)).all() == []

    def test_models_endpoint_uses_provider_source_filter(self, client, monkeypatch):
        registry = _registry(
            {
                OLLAMA: FakeLLM(OLLAMA, ["qwen"]),
                OPENAI: _openai_listing(["text-embedding-3-small", "gpt-4o-mini"]),
            },
            settings={
                OLLAMA: _provider(OLLAMA, "*", "qwen"),
                OPENAI: _provider(OPENAI, "*", "gpt-4o-mini"),
            },
        )
        monkeypatch.setattr("app.services.llm.effective_registry", lambda _db: registry)

        response = client.get(f"{API_PREFIX}/system/llm/models")

        assert response.status_code == 200
        openai_provider = next(
            item for item in response.json()["providers"] if item["provider"] == "openai"
        )
        assert [model["name"] for model in openai_provider["models"]] == ["gpt-4o-mini"]

    def test_candidate_validation_uses_provider_source_filter(self, client, monkeypatch):
        from app.api.routes import llm_config

        candidate = _registry(
            {
                OLLAMA: FakeLLM(OLLAMA, ["qwen"]),
                OPENAI: _openai_listing(["text-embedding-3-small", "gpt-4o-mini"]),
            },
            settings={
                OLLAMA: _provider(OLLAMA, "*", "qwen"),
                OPENAI: _provider(OPENAI, "*", "gpt-4o-mini"),
            },
        )
        monkeypatch.setattr(llm_config, "registry_for_candidate", lambda *_args, **_kwargs: candidate)
        monkeypatch.setattr(llm_config, "_require_external_consent", lambda *_args, **_kwargs: None)

        response = client.post(
            f"{API_PREFIX}/system/llm/providers/config/openai/validate",
            json={"api_key": "candidate-key"},
        )

        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert [model["name"] for model in response.json()["models"]] == ["gpt-4o-mini"]

    def test_validation_error_redacts_candidate_key(self, client, db, monkeypatch, caplog):
        from app.api.routes import llm_config

        secret = "validation-secret-value"
        error_registry = _registry(
            {
                OLLAMA: FakeLLM(OLLAMA, ["qwen"]),
                LLMProvider.custom: FakeLLM(
                    LLMProvider.custom,
                    list_error=LLMAuthError(f"custom rejected key {secret}"),
                ),
            },
            settings={
                OLLAMA: _provider(OLLAMA, "*", "qwen"),
                LLMProvider.custom: ProviderSettings(
                    spec=SPECS[LLMProvider.custom],
                    base_url="http://vllm:8000/v1",
                    models=ModelSelection.parse("*"),
                    default_model=None,
                ),
            },
        )
        monkeypatch.setattr(llm_config, "registry_for_candidate", lambda *_args, **_kwargs: error_registry)

        response = client.post(
            f"{API_PREFIX}/system/llm/providers/config/custom/validate",
            json={"api_key": secret, "base_url": "http://vllm:8000/v1"},
        )

        assert response.status_code == 200
        assert response.json()["ok"] is False
        assert secret not in response.text
        assert "[redacted]" in response.json()["detail"]
        assert secret not in caplog.text
        assert db.exec(select(LLMProviderCredential)).all() == []

    def test_custom_local_url_needs_no_consent_but_remote_does(self, client, db):
        local = client.put(
            f"{API_PREFIX}/system/llm/providers/config/custom",
            json={"base_url": "http://host.docker.internal:8000/v1"},
        )
        assert local.status_code == 200

        blocked = client.put(
            f"{API_PREFIX}/system/llm/providers/config/custom",
            json={"base_url": "https://llm.example/v1"},
        )
        assert blocked.status_code == 422
        assert blocked.json()["error_code"] == "LLM_EXTERNAL_CONSENT_REQUIRED"

        consent = client.put(
            f"{API_PREFIX}/system/llm/external-consent",
            json={"allow_external": True},
        )
        assert consent.status_code == 200
        assert consent.json()["allow_external"] is True

        allowed = client.put(
            f"{API_PREFIX}/system/llm/providers/config/custom",
            json={"base_url": "https://llm.example/v1"},
        )
        assert allowed.status_code == 200

    def test_external_consent_422_does_not_echo_candidate_key(self, client, db, caplog):
        secret = "candidate-secret-never-echo"

        response = client.put(
            f"{API_PREFIX}/system/llm/providers/config/openai",
            json={"api_key": secret},
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "LLM_EXTERNAL_CONSENT_REQUIRED"
        assert secret not in response.text
        assert secret not in caplog.text
        assert db.exec(select(LLMProviderCredential)).all() == []

    def test_secret_key_unavailable_is_503_without_echoing_key(self, client, db, monkeypatch, tmp_path, caplog):
        from app.core import config
        from app.services.llm import user_config

        blocker = tmp_path / "not-a-directory"
        blocker.write_text("x", encoding="ascii")
        monkeypatch.setattr(config, "LLM_SECRET_KEY", "")
        monkeypatch.setattr(config, "LLM_SECRET_KEY_FILE", blocker / "key")
        secret = "candidate-secret-not-echoed"
        user_config.invalidate_registry_cache()
        try:
            response = client.put(
                f"{API_PREFIX}/system/llm/providers/config/custom",
                json={"api_key": secret, "base_url": "http://vllm:8000/v1"},
            )

            assert response.status_code == 503
            assert response.json()["error_code"] == "LLM_SECRET_KEY_UNAVAILABLE"
            assert secret not in response.text
            assert secret not in caplog.text
            assert db.exec(select(LLMProviderCredential)).all() == []
        finally:
            user_config.invalidate_registry_cache()

    def test_credential_status_reports_unreadable_saved_key(self, client, db, monkeypatch, test_registry, tmp_path):
        from app.core import config
        from app.services.llm import user_config

        encrypted = "saved-ciphertext-never-returned"
        db.add(LLMProviderCredential(provider="openai", api_key_encrypted=encrypted))
        db.commit()
        monkeypatch.setattr(config, "LLM_SECRET_KEY", "")
        monkeypatch.setattr(config, "LLM_SECRET_KEY_FILE", tmp_path / "missing.key")
        user_config._invalid_credentials.clear()
        user_config._warned_credential_errors.clear()
        assert user_config.decrypt_api_key(encrypted, "openai") is None
        monkeypatch.setattr(user_config, "_build_registry", lambda *_args, **_kwargs: test_registry)
        user_config.invalidate_registry_cache()
        try:
            response = client.get(f"{API_PREFIX}/system/llm/providers/config")

            assert response.status_code == 200
            openai_status = next(
                item for item in response.json()["providers"] if item["provider"] == "openai"
            )
            assert openai_status["credential_status"] == "unavailable"
            assert encrypted not in response.text
        finally:
            user_config.invalidate_registry_cache()

    def test_models_endpoint_marks_manual_model(self, client, db, monkeypatch):
        db.add(LLMManualModel(provider="gemini", model="manual-model"))
        db.commit()
        settings = {
            OLLAMA: _provider(OLLAMA, "*", "qwen"),
            GEMINI: ProviderSettings(
                spec=SPECS[GEMINI],
                base_url="http://local:1",
                models=ModelSelection.parse("g1,manual-model"),
                default_model="g1",
                manual_models=("manual-model",),
            ),
        }
        manual_registry = _registry(
            {OLLAMA: FakeLLM(OLLAMA, ["qwen"]), GEMINI: FakeLLM(GEMINI, ["g1"])},
            settings=settings,
        )
        monkeypatch.setattr("app.services.llm.effective_registry", lambda _db: manual_registry)

        response = client.get(f"{API_PREFIX}/system/llm/models")

        assert response.status_code == 200
        model = next(
            item
            for provider in response.json()["providers"]
            if provider["provider"] == "gemini"
            for item in provider["models"]
            if item["name"] == "manual-model"
        )
        assert model["manual"] is True

    def test_manual_model_endpoint_validates_persists_and_lists_model(self, client, db, monkeypatch):
        from app.api.routes import llm_config

        db.add(LLMProviderCredential(provider="custom", base_url="http://vllm:8000/v1"))
        db.commit()
        settings = {
            OLLAMA: _provider(OLLAMA, "*", "qwen"),
            LLMProvider.custom: ProviderSettings(
                spec=SPECS[LLMProvider.custom],
                base_url="http://vllm:8000/v1",
                models=ModelSelection.parse("manual-model"),
                default_model=None,
                manual_models=("manual-model",),
            ),
        }
        manual_registry = _registry(
            {
                OLLAMA: FakeLLM(OLLAMA, ["qwen"]),
                LLMProvider.custom: FakeLLM(LLMProvider.custom, []),
            },
            settings=settings,
        )
        monkeypatch.setattr(llm_config, "registry_for_candidate", lambda *_args, **_kwargs: manual_registry)
        monkeypatch.setattr("app.services.llm.effective_registry", lambda _db: manual_registry)

        response = client.post(
            f"{API_PREFIX}/system/llm/providers/config/custom/models",
            json={"model": "manual-model"},
        )

        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert [model.model for model in db.exec(select(LLMManualModel)).all()] == ["manual-model"]

        catalog = client.get(f"{API_PREFIX}/system/llm/models").json()["providers"]
        custom = next(provider for provider in catalog if provider["provider"] == "custom")
        assert {"name": "manual-model", "manual": True} in custom["models"]

    def test_deleting_provider_config_also_deletes_manual_models(self, client, db):
        db.add(LLMProviderCredential(provider="gemini", key_hint="hint"))
        db.add(LLMManualModel(provider="gemini", model="manual-model"))
        db.commit()

        response = client.delete(f"{API_PREFIX}/system/llm/providers/config/gemini")

        assert response.status_code == 200
        assert db.exec(select(LLMProviderCredential)).all() == []
        assert db.exec(select(LLMManualModel)).all() == []

    def test_list_models(self, client, ollama_offers):
        # ollama_offers uses ModelInfo(name=n) without extra fields; FastAPI omits
        # null fields, so models appear as {"name": "..."}.
        # qwen2.5:1.5b is offered → not downloadable.
        # qwen2.5:3b / :7b and llama3.2:3b are in the default installable set
        # but not offered → they appear in downloadable.
        ollama_offers("qwen2.5:1.5b", "llama3:8b")
        resp = client.get(f"{API_PREFIX}/system/llm/models")
        assert resp.status_code == 200
        assert resp.json() == {
            "default": {"provider": "ollama", "model": "qwen2.5:1.5b"},
            "providers": [{
                "provider": "ollama",
                "available": True,
                "default_model": "qwen2.5:1.5b",
                "models": [{"name": "qwen2.5:1.5b"}, {"name": "llama3:8b"}],
                "downloadable": [
                    {"name": "qwen2.5:3b", "installed": False},
                    {"name": "qwen2.5:7b", "installed": False},
                    {"name": "llama3.2:3b", "installed": False},
                ],
            }],
        }

    def test_downloadable_omitted_when_all_installable_models_are_installed(self, client, ollama_offers):
        ollama_offers(*DEFAULT_OLLAMA_INSTALLABLE_MODELS)

        resp = client.get(f"{API_PREFIX}/system/llm/models")

        assert resp.status_code == 200
        provider = resp.json()["providers"][0]
        assert "downloadable" not in provider

    def test_list_models_provider_down(self, client, monkeypatch):
        import requests

        def boom(*a, **k):
            raise requests.exceptions.ConnectionError("down")

        monkeypatch.setattr("app.services.llm.ollama.requests.request", boom)
        provider = client.get(f"{API_PREFIX}/system/llm/models").json()["providers"][0]
        assert provider["available"] is False
        assert provider["error_code"] == "LLM_UNAVAILABLE"
        assert provider["models"] == []
        assert "Could not reach Ollama" in provider["detail"]

    def test_test_model_ok(self, client, test_llm, monkeypatch):
        monkeypatch.setattr(test_llm, "_generate", lambda prompt, schema, model: '{"ok": true}')
        resp = client.post(f"{API_PREFIX}/system/llm/test", json={"model": "llama3:8b"})
        assert resp.status_code == 200
        body = resp.json()
        assert (body["provider"], body["model"], body["ok"]) == ("ollama", "llama3:8b", True)

    def test_test_model_without_body_uses_default(self, client, test_llm, monkeypatch):
        monkeypatch.setattr(test_llm, "_generate", lambda prompt, schema, model: '{"ok": true}')
        body = client.post(f"{API_PREFIX}/system/llm/test").json()
        assert (body["provider"], body["model"], body["ok"]) == ("ollama", "qwen2.5:1.5b", True)

    def test_test_model_failure(self, client, test_llm, monkeypatch):
        def fail(prompt, schema, model):
            raise LLMUnavailableError("Ollama at http://ollama:11434 timed out")

        monkeypatch.setattr(test_llm, "_generate", fail)
        body = client.post(f"{API_PREFIX}/system/llm/test", json={}).json()
        assert body["ok"] is False
        assert body["detail"] == "Ollama at http://ollama:11434 timed out"

    def test_test_model_disabled_provider(self, client):
        resp = client.post(f"{API_PREFIX}/system/llm/test", json={"provider": "gemini"})
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "LLM_NOT_AVAILABLE"

    def test_fill_refuses_model_the_provider_lacks(self, client, db, ollama_offers):
        """Refused before anything is stored, including the input for input_text."""
        ollama_offers("qwen2.5:1.5b")
        tpl = client.post(f"{API_PREFIX}/templates/create", json={
            "name": "T", "description": "d", "pdf_path": "src/inputs/t.pdf", "fields": {"name": "string"},
        }).json()["id"]
        resp = client.post(f"{API_PREFIX}/forms/fill", json={
            "template_id": tpl, "input_text": "fire", "model": "llama3:8b",
        })
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "LLM_NOT_AVAILABLE"
        assert db.exec(select(Input)).all() == []

    def test_llm_failure_is_answered_and_logged(
        self, client, test_llm, mock_controller, tmp_path, monkeypatch, caplog
    ):
        """A rejected key reaches the client as LLM_AUTH_FAILED and the log as one line."""
        from app.services.form_filler import filler

        def reject(prompt, schema, model):
            raise LLMAuthError("gemini rejected the API key: Please pass a valid API key. Check GEMINI_API_KEY.")

        monkeypatch.setattr(test_llm, "_generate", reject)
        # Skip the PDF work, go straight to the LLM call the real filler makes
        mock_controller["mock_fill"].side_effect = lambda **kw: filler.call_model(
            "prompt", {}, kw["model"], kw["provider"]
        )
        monkeypatch.setattr("app.core.paths.PROJECT_ROOT", tmp_path)
        (tmp_path / "t.pdf").write_bytes(b"%PDF-1.4 fake")
        tpl = client.post(f"{API_PREFIX}/templates/create", json={
            "name": "T", "description": "d", "pdf_path": "t.pdf", "fields": {"name": "string"},
        }).json()["id"]

        resp = client.post(f"{API_PREFIX}/forms/fill", json={"template_id": tpl, "input_text": "fire"})

        assert resp.status_code == 502
        assert resp.json()["error_code"] == "LLM_AUTH_FAILED"
        assert "Check GEMINI_API_KEY" in resp.json()["message"]
        logged = [r.getMessage() for r in caplog.records if r.name == "app.core.errors.handlers"]
        assert logged == [
            "POST /api/v1/forms/fill failed with 502 LLM_AUTH_FAILED: "
            "gemini rejected the API key: Please pass a valid API key. Check GEMINI_API_KEY."
        ]

    def test_wrong_settings_are_an_error_response(self, client, monkeypatch):
        """The app stays up and says what to fix, instead of crashing at startup."""
        from app.services.llm import LLMConfigError

        def broken():
            raise LLMConfigError("GEMINI_API_KEY is set but GEMINI_MODELS is empty.")

        monkeypatch.setattr("app.services.llm.get_registry", broken)

        resp = client.get(f"{API_PREFIX}/system/llm/models")
        assert resp.status_code == 500
        assert resp.json() == {
            "error_code": "LLM_CONFIG_ERROR",
            "message": "GEMINI_API_KEY is set but GEMINI_MODELS is empty.",
        }
        llm_health = client.get(f"{API_PREFIX}/health").json()["components"]["llm"]
        assert llm_health["status"] == "unhealthy"
        assert llm_health["detail"] == "GEMINI_API_KEY is set but GEMINI_MODELS is empty."

    def test_jobs_refuse_disabled_provider(self, client, db, monkeypatch):
        queued = []
        monkeypatch.setattr("app.api.routes.jobs.fill_form_task.apply_async", lambda *a, **k: queued.append(a))
        tpl = client.post(f"{API_PREFIX}/templates/create", json={
            "name": "T", "description": "d", "pdf_path": "src/inputs/t.pdf", "fields": {"name": "string"},
        }).json()["id"]
        record = Input(input_type=InputType.text, status=InputStatus.ready, transcript="fire")
        db.add(record)
        db.commit()

        resp = client.post(f"{API_PREFIX}/forms/jobs", json={
            "template_ids": [tpl], "input_id": str(record.input_id), "provider": "anthropic",
        })
        assert resp.status_code == 422
        assert queued == []


class TestPullEndpoint:

    _PULL = f"{API_PREFIX}/system/llm/pull"

    def test_pull_success_ndjson_and_refreshes_catalog(self, client, test_llm, monkeypatch):
        import json

        offered = ["qwen2.5:1.5b"]
        monkeypatch.setattr(
            test_llm, "list_models", lambda: [ModelInfo(name=n) for n in offered]
        )

        before = client.get(f"{API_PREFIX}/system/llm/models")
        assert before.status_code == 200
        before_models = before.json()["providers"][0]["models"]
        assert {"name": "qwen2.5:3b"} not in before_models

        events = []

        def pull(model, on_success=None):
            yield '{"status": "pulling manifest"}\n'
            yield '{"status": "success"}\n'
            events.append("success-line-consumed")
            offered.append("qwen2.5:3b")
            if on_success:
                on_success()
                events.append("catalog-refreshed")

        monkeypatch.setattr(test_llm, "pull_model", pull)

        resp = client.post(self._PULL, json={"model": "qwen2.5:3b"})
        assert resp.status_code == 200
        assert "application/x-ndjson" in resp.headers["content-type"]
        lines = [json.loads(line) for line in resp.text.strip().split("\n") if line.strip()]
        assert lines[-1]["status"] == "success"
        assert events == ["success-line-consumed", "catalog-refreshed"]

        models = client.get(f"{API_PREFIX}/system/llm/models").json()["providers"][0]["models"]
        assert {"name": "qwen2.5:3b"} in models

    def test_pull_rejects_non_ollama_provider(self, client):
        resp = client.post(self._PULL, json={"provider": "gemini", "model": "gemini-2.5-flash"})
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "LLM_NOT_AVAILABLE"

    def test_pull_rejects_unauthorized_model(self, client):
        resp = client.post(self._PULL, json={"model": "not-in-installable-set:99b"})
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "LLM_NOT_AVAILABLE"

    def test_pull_rejects_invalid_model_name(self, client):
        resp = client.post(self._PULL, json={"model": "bad name!"})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error_code"] == "VALIDATION_ERROR"

    def test_pull_503_when_ollama_down_before_stream(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.services.llm.ollama.requests.post",
            lambda *a, **k: (_ for _ in ()).throw(requests.exceptions.ConnectionError("down")),
        )
        resp = client.post(self._PULL, json={"model": "qwen2.5:3b"})
        assert resp.status_code == 503
        assert resp.json()["error_code"] == "LLM_UNAVAILABLE"

    def test_pull_mid_stream_error_without_success(self, client, test_llm, monkeypatch):
        import json

        def pull(model, on_success=None):
            yield '{"status": "downloading"}\n'
            yield '{"error": "disk full"}\n'

        monkeypatch.setattr(test_llm, "pull_model", pull)
        resp = client.post(self._PULL, json={"model": "qwen2.5:3b"})
        assert resp.status_code == 200
        lines = [json.loads(line) for line in resp.text.strip().split("\n") if line.strip()]
        assert any("error" in p for p in lines)
        assert not any(p.get("status") == "success" for p in lines)


class TestDeleteEndpoint:

    _DELETE = f"{API_PREFIX}/system/llm/models"

    def test_delete_success_refreshes_catalog(self, client, test_llm, monkeypatch):
        offered = ["qwen2.5:1.5b", "qwen2.5:3b"]
        monkeypatch.setattr(
            test_llm,
            "list_models",
            lambda: [ModelInfo(name=name, installed=True) for name in offered],
        )

        before = client.get(f"{API_PREFIX}/system/llm/models")
        assert before.status_code == 200
        before_models = before.json()["providers"][0]["models"]
        assert any(model["name"] == "qwen2.5:3b" for model in before_models)

        deleted = []

        def delete_model(model):
            deleted.append(model)
            offered.remove(model)

        monkeypatch.setattr(test_llm, "delete_model", delete_model)
        response = client.request("DELETE", self._DELETE, json={"model": "qwen2.5:3b"})

        assert response.status_code == 200
        assert response.json() == {"model": "qwen2.5:3b", "deleted": True}
        assert deleted == ["qwen2.5:3b"]
        after = client.get(f"{API_PREFIX}/system/llm/models").json()["providers"][0]
        assert not any(model["name"] == "qwen2.5:3b" for model in after["models"])
        assert any(
            model["name"] == "qwen2.5:3b" and model["installed"] is False
            for model in after["downloadable"]
        )

    def test_delete_rejects_invalid_model_name(self, client):
        response = client.request("DELETE", self._DELETE, json={"model": "bad model!"})

        assert response.status_code == 422
        assert response.json()["error_code"] == "VALIDATION_ERROR"

    def test_delete_rejects_non_ollama_provider(self, client):
        response = client.request(
            "DELETE",
            self._DELETE,
            json={"provider": "gemini", "model": "gemini-2.5-flash"},
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "LLM_NOT_AVAILABLE"

    def test_delete_rejects_when_ollama_disabled(self, client, monkeypatch):
        settings = LLMSettings(
            providers={GEMINI: _provider(GEMINI, "g1", "g1")},
            default_provider=GEMINI,
        )
        disabled_registry = LLMRegistry(settings, {GEMINI: FakeLLM(GEMINI, ["g1"])})
        monkeypatch.setattr(
            "app.api.routes.llm.llm.effective_registry",
            lambda _db: disabled_registry,
        )

        response = client.request("DELETE", self._DELETE, json={"model": "qwen2.5:3b"})

        assert response.status_code == 422
        assert response.json()["error_code"] == "LLM_NOT_AVAILABLE"

    def test_delete_rejects_model_outside_ollama_models(self, client):
        response = client.request("DELETE", self._DELETE, json={"model": "secret:model"})

        assert response.status_code == 422
        assert response.json()["error_code"] == "LLM_NOT_AVAILABLE"

    def test_delete_returns_not_installed_for_missing_model(self, client, test_llm, monkeypatch):
        monkeypatch.setattr(
            test_llm,
            "list_models",
            lambda: [
                ModelInfo(name="qwen2.5:1.5b", installed=True),
                ModelInfo(name="qwen2.5:3b", manual=True),
            ],
        )
        delete = MagicMock()
        monkeypatch.setattr(test_llm, "delete_model", delete)

        response = client.request("DELETE", self._DELETE, json={"model": "qwen2.5:3b"})

        assert response.status_code == 404
        assert response.json()["error_code"] == "LLM_MODEL_NOT_INSTALLED"
        delete.assert_not_called()

    def test_delete_rejects_global_default_model(self, client, test_llm, monkeypatch):
        monkeypatch.setattr(
            test_llm,
            "list_models",
            lambda: [ModelInfo(name="qwen2.5:1.5b", installed=True)],
        )

        response = client.request("DELETE", self._DELETE, json={"model": "qwen2.5:1.5b"})

        assert response.status_code == 409
        assert response.json()["error_code"] == "LLM_MODEL_IN_USE"
        assert "global default" in response.json()["message"]

    def test_delete_rejects_ollama_provider_default(self, client, test_registry, test_llm, monkeypatch):
        settings = LLMSettings(
            providers={
                OLLAMA: test_registry.settings.providers[OLLAMA],
                GEMINI: _provider(GEMINI, "g1", "g1"),
            },
            default_provider=GEMINI,
        )
        registry = LLMRegistry(
            settings,
            {OLLAMA: test_llm, GEMINI: FakeLLM(GEMINI, ["g1"])},
        )
        monkeypatch.setattr(
            "app.api.routes.llm.llm.effective_registry",
            lambda _db: registry,
        )
        monkeypatch.setattr(
            test_llm,
            "list_models",
            lambda: [ModelInfo(name="qwen2.5:1.5b", installed=True)],
        )

        response = client.request("DELETE", self._DELETE, json={"model": "qwen2.5:1.5b"})

        assert response.status_code == 409
        assert response.json()["error_code"] == "LLM_MODEL_IN_USE"
        assert "Ollama provider default" in response.json()["message"]

    def test_delete_rejects_model_with_active_pull(self, client, test_llm, monkeypatch):
        from app.services.llm.ollama import _register_active_pull, _unregister_active_pull

        model = "qwen2.5:3b"
        monkeypatch.setattr(
            test_llm,
            "list_models",
            lambda: [
                ModelInfo(name="qwen2.5:1.5b", installed=True),
                ModelInfo(name=model, installed=True),
            ],
        )
        _register_active_pull(model)
        try:
            response = client.request("DELETE", self._DELETE, json={"model": model})
        finally:
            _unregister_active_pull(model)

        assert response.status_code == 409
        assert response.json()["error_code"] == "LLM_MODEL_IN_USE"
        assert "download is currently active" in response.json()["message"]
