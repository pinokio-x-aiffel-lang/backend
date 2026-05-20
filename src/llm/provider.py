from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    api_key_env: str
    base_url_env: str | None = None


@dataclass(frozen=True)
class ModelConfig:
    alias: str
    provider: str
    supports_json_object: bool = False
    supports_json_schema: bool = False


PROVIDERS: dict[str, ProviderConfig] = {
    "openai": ProviderConfig(
        name="openai",
        api_key_env="OPENAI_API_KEY",
        base_url_env=None,  # OpenAI SDK 기본 URL 사용
    ),
    "hyperclova": ProviderConfig(
        name="hyperclova",
        api_key_env="CLOVASTUDIO_API_KEY",
        base_url_env="CLOVASTUDIO_BASE_URL",
    ),
    "anthropic": ProviderConfig(
        name="anthropic",
        api_key_env="ANTHROPIC_API_KEY",
        base_url_env="ANTHROPIC_BASE_URL",
    ),
    "gemini": ProviderConfig(
        name="gemini",
        api_key_env="GEMINI_API_KEY",
        base_url_env="GEMINI_BASE_URL",
    ),
}


# alias: 실제 모델명 아님. 프로젝트 내에서 “이 호출이 어떤 용도인지” 나타내는 이름. 
MODELS: dict[str, ModelConfig] = {
    "claim-detection-openai": ModelConfig(
        alias="claim-detection-openai",
        provider="openai",
        supports_json_object=True,
        supports_json_schema=True,
    ),
    "claim-detection-hyperclova": ModelConfig(
        alias="claim-detection-hyperclova",
        provider="hyperclova",
        supports_json_object=True,
        supports_json_schema=True,
    ),
    "claim-detection-claude": ModelConfig(
        alias="claim-detection-claude",
        provider="anthropic",
        supports_json_object=False,
        supports_json_schema=False,
    ),
    "claim-detection-gemini": ModelConfig(
        alias="claim-detection-gemini",
        provider="gemini",
        supports_json_object=True,
        supports_json_schema=True,
    ),
}