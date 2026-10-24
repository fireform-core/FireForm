"""Every enabled provider, and which of their models a request may pick.

    registry = llm.get_registry()
    choice = registry.resolve("gemini", "gemini-2.5-flash")   # raises if it can't run
    text = registry.generate_json(prompt, schema, choice.provider, choice.model)

The model lists come from the providers themselves and are cached briefly,
so a picked model is one the provider actually offers right now.
"""

import logging
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace

from app.api.schemas.enums import LLMProvider
from app.services.llm.base import DownloadableModelInfo, LLM, ModelInfo
from app.services.llm.errors import LLMError, LLMNotAvailableError, LLMResponseError
from app.services.llm.factory import create_llm
from app.services.llm.settings import LLMSettings, ProviderSettings
from app.services.llm.specs import DEFAULT_OLLAMA_INSTALLABLE_MODELS

logger = logging.getLogger(__name__)

# A reachable provider's list rarely changes. A failure is kept for less time so
# a provider that comes back is usable again quickly.
CACHE_SECONDS = 60
FAILURE_CACHE_SECONDS = 10


@dataclass(frozen=True)
class ModelChoice:
    provider: LLMProvider
    model: str


@dataclass(frozen=True)
class ProviderCatalog:
    provider: LLMProvider
    available: bool
    models: tuple[ModelInfo, ...]
    default_model: str | None = None
    # Why the provider is unavailable
    detail: str | None = None
    error_code: str | None = None
    # Names in <PREFIX>_MODELS the provider doesn't offer, left out of models
    missing: tuple[str, ...] = ()
    downloadable: tuple[DownloadableModelInfo, ...] = ()
    error: LLMError | None = field(default=None, compare=False, repr=False)

    def offers(self, model: str) -> bool:
        return any(m.name == model for m in self.models)


class LLMRegistry:
    def __init__(
        self,
        settings: LLMSettings,
        clients: Mapping[LLMProvider, LLM],
        clock: Callable[[], float] = time.monotonic,
    ):
        self.settings = settings
        self._clients = dict(clients)
        self._clock = clock
        self._cache: dict[LLMProvider, tuple[float, ProviderCatalog]] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_settings(
        cls, settings: LLMSettings, build: Callable[[ProviderSettings], LLM] = create_llm
    ) -> "LLMRegistry":
        return cls(settings, {p: build(s) for p, s in settings.providers.items()})

    @property
    def providers(self) -> list[LLMProvider]:
        return list(self._clients)

    @property
    def default(self) -> ModelChoice:
        return ModelChoice(self.settings.default_provider, self.settings.default_model)

    def client(self, provider: LLMProvider) -> LLM:
        try:
            return self._clients[provider]
        except KeyError:
            raise LLMNotAvailableError(self._not_enabled(provider)) from None

    def catalog(self, refresh: bool = False) -> list[ProviderCatalog]:
        """Every enabled provider and its models. Providers are asked in parallel."""
        with ThreadPoolExecutor(max_workers=max(len(self._clients), 1)) as pool:
            return list(pool.map(lambda p: self.provider_catalog(p, refresh), self._clients))

    def provider_catalog(self, provider: LLMProvider, refresh: bool = False) -> ProviderCatalog:
        settings = self._settings_for(provider)
        now = self._clock()
        with self._lock:
            cached = self._cache.get(provider)
        if cached and not refresh:
            read_at, listing = cached
            ttl = CACHE_SECONDS if listing.available else FAILURE_CACHE_SECONDS
            if now - read_at < ttl:
                return listing

        listing = self._read(settings)
        with self._lock:
            self._cache[provider] = (now, listing)
        if cached and cached[1].available != listing.available:
            self._log_change(listing)
        return listing

    def resolve(
        self, provider: LLMProvider | str | None = None, model: str | None = None, verify: bool = True
    ) -> ModelChoice:
        """Turn what a request asked for into a provider and model that can run.

        Missing parts fall back to the defaults. Raises LLMNotAvailableError when
        the pair isn't enabled or offered, and LLMUnavailableError when the
        provider can't be reached. verify=False skips asking the provider, for
        callers that are about to send it a prompt anyway.
        """
        provider = self._parse_provider(provider)
        settings = self._settings_for(provider)
        model = model or settings.default_model
        if not model:
            raise LLMNotAvailableError(f"{provider.value} has no default model. Name one.")
        choice = ModelChoice(provider, model)

        # The default was checked at startup, every fill without a model lands here
        if choice == self.default:
            return choice
        if not settings.models.allows(model):
            raise LLMNotAvailableError(
                f"{model} is not in {settings.spec.setting('MODELS')}. Pick one GET /system/llm/models lists."
            )
        if not verify:
            return choice

        listing = self.provider_catalog(provider)
        if listing.error:
            # Same type as the original, so a wrong key stays LLM_AUTH_FAILED
            raise type(listing.error)(listing.error.message)
        if not listing.offers(model):
            raise LLMNotAvailableError(
                f"{provider.value} does not offer {model}. Pick one GET /system/llm/models lists."
            )
        return choice

    def generate_json(
        self, prompt: str, schema: dict, provider: LLMProvider | str | None = None, model: str | None = None
    ) -> str:
        choice = self.resolve(provider, model)
        return self.client(choice.provider).generate_json(prompt, schema, choice.model)

    def _read(self, settings: ProviderSettings) -> ProviderCatalog:
        try:
            offered = self._clients[settings.provider].list_models()
        except LLMError as exc:
            if (
                settings.manual_models
                and isinstance(exc, LLMResponseError)
                and "has no model list" in exc.message
            ):
                offered = []
            else:
                return ProviderCatalog(
                    settings.provider,
                    available=False,
                    models=(),
                    default_model=settings.default_model,
                    detail=exc.message,
                    error_code=exc.error_code,
                    error=exc,
                )
        if settings.manual_models:
            offered_by_name = {model.name: model for model in offered}
            for name in settings.manual_models:
                if name in offered_by_name:
                    offered_by_name[name] = replace(offered_by_name[name], manual=True)
                else:
                    offered_by_name[name] = ModelInfo(name=name, manual=True)
            offered = list(offered_by_name.values())
        kept, missing = settings.models.pick(offered)
        offered_names = {m.name for m in offered}

        downloadable: list[DownloadableModelInfo] = []
        if settings.provider is LLMProvider.ollama:
            if settings.models.wildcard:
                candidate_names = settings.installable_models or DEFAULT_OLLAMA_INSTALLABLE_MODELS
                downloadable = [
                    DownloadableModelInfo(name=name, installed=False)
                    for name in candidate_names
                    if name not in offered_names
                ]
            else:
                downloadable = [
                    DownloadableModelInfo(name=name, installed=False)
                    for name in missing
                ]

        return ProviderCatalog(
            settings.provider,
            available=True,
            models=tuple(kept),
            default_model=settings.default_model,
            missing=tuple(missing),
            downloadable=tuple(downloadable),
        )

    def validate_pull(self, provider: LLMProvider | str | None, model: str) -> None:
        """Validate that provider is ollama, enabled, and model is in the installable set."""
        provider_enum = self._parse_provider(provider)
        if provider_enum is not LLMProvider.ollama:
            raise LLMNotAvailableError("Model pulling is only supported for Ollama.")
        if LLMProvider.ollama not in self._clients:
            raise LLMNotAvailableError(self._not_enabled(LLMProvider.ollama))

        settings = self._settings_for(LLMProvider.ollama)
        if settings.models.wildcard:
            allowed = settings.installable_models or DEFAULT_OLLAMA_INSTALLABLE_MODELS
            if model not in allowed:
                raise LLMNotAvailableError(
                    f"{model} cannot be pulled. With OLLAMA_MODELS=*, allowed models are: {', '.join(allowed)}."
                )
        else:
            if not settings.models.allows(model):
                raise LLMNotAvailableError(
                    f"{model} is not in OLLAMA_MODELS. Allowed: {', '.join(settings.models.names)}."
                )

    def _settings_for(self, provider: LLMProvider) -> ProviderSettings:
        try:
            return self.settings.providers[provider]
        except KeyError:
            raise LLMNotAvailableError(self._not_enabled(provider)) from None

    def _parse_provider(self, provider: LLMProvider | str | None) -> LLMProvider:
        if provider is None:
            return self.settings.default_provider
        try:
            return LLMProvider(provider)
        except ValueError:
            raise LLMNotAvailableError(
                f"{provider!r} is not a provider. Use one of: {', '.join(p.value for p in self.providers)}."
            ) from None

    @staticmethod
    def _log_change(listing: ProviderCatalog) -> None:
        """Log a provider going down or coming back. The first read is left to
        the startup check, so it isn't logged twice."""
        if listing.available:
            logger.info("LLM provider %s is available again", listing.provider.value)
        else:
            logger.warning("LLM provider %s is unavailable: %s", listing.provider.value, listing.detail)

    @staticmethod
    def _not_enabled(provider: LLMProvider) -> str:
        return f"{provider.value} is not enabled on this server."
