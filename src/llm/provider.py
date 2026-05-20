from dataclasses import dataclass

CLOVASTUDIO_BASE_URL = "https://clovastudio.stream.ntruss.com/v1/openai"
CLOVASTUDIO_BASE_URL_STRUCTURED = "https://clovastudio.stream.ntruss.com/v3/chat-completions/HCX-007"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"

@dataclass(frozen=True)
class ProviderConfig:
    model_alias: str
    api_key_env: str
    supports_json_object: bool
    supports_structured_output: bool
    base_url: str | None = None
    native_url: str | None = None  # v3 native endpoint (httpx 직접 호출용)


PROVIDERS: dict[str, ProviderConfig] = {
    "openai": ProviderConfig(
        model_alias="openai",
        api_key_env="OPENAI_API_KEY",
        supports_json_object=True,
        supports_structured_output=True,
    ),
    "hyperclova": ProviderConfig(
        model_alias="hyperclova",
        api_key_env="CLOVASTUDIO_API_KEY",
        supports_json_object=True,
        supports_structured_output=True,
        base_url=CLOVASTUDIO_BASE_URL,
        native_url=CLOVASTUDIO_BASE_URL_STRUCTURED,
    ),
    "claude": ProviderConfig(
        model_alias="claude",
        api_key_env="ANTHROPIC_API_KEY",
        supports_json_object=False,
        supports_structured_output=False,
        base_url=ANTHROPIC_BASE_URL,
    ),
    "gemini": ProviderConfig(
        model_alias="gemini",
        api_key_env="GEMINI_API_KEY",
        supports_json_object=True,
        supports_structured_output=True,
        base_url=GEMINI_BASE_URL,
    ),
}
