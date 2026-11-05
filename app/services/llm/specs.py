"""What each provider needs, as data.

Adding a provider means adding an LLMProvider value and a row here. Nothing
else branches on the provider, apart from factory.py picking the Ollama
transport for Ollama.
"""

from dataclasses import dataclass

from app.api.schemas.enums import LLMProvider


@dataclass(frozen=True)
class ProviderSpec:
    provider: LLMProvider
    default_base_url: str = ""
    needs_key: bool = True
    structured_output: bool = True
    max_tokens: int | None = None
    headers: tuple[tuple[str, str], ...] = ()
    listed_id_prefix: str = ""
    native_model_list_url: str = ""
    native_model_list_api_key_header: str = ""
    required_generation_method: str = ""
    model_list_page_limit: int = 20
    excluded_id_markers: tuple[str, ...] = ()

    @property
    def prefix(self) -> str:
        """Start of every setting for this provider, such as GEMINI in GEMINI_MODELS."""
        return self.provider.value.upper()

    def setting(self, key: str) -> str:
        """Full name of one setting, for error messages. OLLAMA_BASE_URL is OLLAMA_HOST."""
        if self.provider is LLMProvider.ollama and key == "BASE_URL":
            return "OLLAMA_HOST"
        return f"{self.prefix}_{key}"


SPECS: dict[LLMProvider, ProviderSpec] = {
    LLMProvider.ollama: ProviderSpec(LLMProvider.ollama, needs_key=False),
    LLMProvider.llama_cpp: ProviderSpec(
        LLMProvider.llama_cpp,
        "http://127.0.0.1:8080/v1",
        needs_key=False,
    ),
    LLMProvider.openai: ProviderSpec(
        LLMProvider.openai,
        "https://api.openai.com/v1",
        excluded_id_markers=(
            "embedding",
            "whisper",
            "tts",
            "dall-e",
            "moderation",
            "transcribe",
            "realtime",
            "image",
            "audio",
        ),
    ),
    LLMProvider.gemini: ProviderSpec(
        LLMProvider.gemini,
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        listed_id_prefix="models/",
        native_model_list_url="https://generativelanguage.googleapis.com/v1beta/models",
        native_model_list_api_key_header="x-goog-api-key",
        required_generation_method="generateContent",
        model_list_page_limit=20,
        excluded_id_markers=(
            "tts",
            "image",
            "banana",
            "lyria",
            "transcribe",
            "robotics",
            "computer",
            "research",
            "antigravity",
            "embedding",
            "imagen",
            "veo",
            "live",
            "aqa",
        ),
    ),
    LLMProvider.anthropic: ProviderSpec(
        LLMProvider.anthropic,
        "https://api.anthropic.com/v1/",
        structured_output=False,
        max_tokens=12288,
        headers=(("anthropic-version", "2023-06-01"),),
    ),
    LLMProvider.custom: ProviderSpec(LLMProvider.custom, needs_key=False),
}

DEFAULT_OLLAMA_INSTALLABLE_MODELS: tuple[str, ...] = (
    "qwen2.5:1.5b",
    "qwen2.5:3b",
    "qwen2.5:7b",
    "llama3.2:3b",
)
