"""Build the client for one provider from its checked settings (settings.py)."""

from app.api.schemas.enums import LLMProvider
from app.services.llm.base import LLM
from app.services.llm.ollama import OllamaLLM
from app.services.llm.openai_compatible import OpenAICompatibleLLM
from app.services.llm.settings import ProviderSettings


def create_llm(settings: ProviderSettings) -> LLM:
    # Ollama has its own transport, every other provider speaks the OpenAI API
    if settings.provider is LLMProvider.ollama:
        return OllamaLLM(
            host=settings.base_url,
            model=settings.default_model,
            timeout=settings.timeout,
            pull_timeout=settings.pull_timeout,
        )
    return OpenAICompatibleLLM(
        provider=settings.provider,
        base_url=settings.base_url,
        api_key=settings.api_key,
        model=settings.default_model,
        timeout=settings.timeout,
        max_retries=settings.max_retries,
        structured_output=settings.structured_output,
        max_tokens=settings.max_tokens,
        temperature=settings.temperature,
        headers=dict(settings.spec.headers),
        listed_id_prefix=settings.spec.listed_id_prefix,
    )
