from dataclasses import dataclass

CLOVASTUDIO_BASE_URL = "https://clovastudio.stream.ntruss.com/v1/openai"
CLOVASTUDIO_BASE_URL_STRUCTURED = "https://clovastudio.stream.ntruss.com/v3/chat-completions/HCX-007"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"

# 출처: https://developers.openai.com/api/docs/models/all (2026-05 기준, 텍스트 생성 + 유료 계정)
GPT_MODELS = [
    # GPT-5.x (최신)
    "gpt-5.5",
    "gpt-5.5-pro",
    "gpt-5.4",
    "gpt-5.4-pro",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    "gpt-5",
    "gpt-5-pro",
    "gpt-5-mini",
    "gpt-5-nano",
    # GPT-4.x
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4o",
    "gpt-4o-mini",
    # o-series (reasoning)
    "o3-pro",
    "o3",
    "o3-mini",
    "o4-mini",
    # legacy
    "o1-pro",
    "o1",
    "o1-mini",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
]

# 출처: https://guide.ncloud-docs.com/docs/clovastudio-model (2026-05 기준)
HCX_MODELS = [
    "HCX-007",
    "HCX-005",
    "HCX-DASH-002",
    "HCX-003",
    "HCX-DASH-001",
]

# context_window: 입력+출력 합산 한도 / max_output_tokens: 출력 단독 한도
# HCX-DASH-001은 context_window(3,500)가 병목 — max_tokens는 입력 길이를 고려해 설정해야 함
HCX_MODEL_INFO: dict[str, dict] = {
    "HCX-007":      {"context_window": 128_000, "max_output_tokens": 32_768},
    "HCX-005":      {"context_window": 128_000, "max_output_tokens":  4_096},
    "HCX-DASH-002": {"context_window":  32_000, "max_output_tokens":  4_096},
    "HCX-003":      {"context_window":   7_600, "max_output_tokens":  4_096},
    "HCX-DASH-001": {"context_window":   3_500, "max_output_tokens":  4_096},
}

# 출처: https://ai.google.dev/gemini-api/docs/models (2026-05 기준, 텍스트 생성 + 무료 tier)
GEMINI_MODELS = [
    # Gemini 3.x (stable)
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    # Gemini 3.x (preview)
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    # Gemini 2.5 (stable)
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    # deprecated — 2026-06-01 이후 사용 불가
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]

# 출처: https://platform.claude.com/docs/en/docs/about-claude/models (2026-05 기준)
CLAUDE_MODELS = [
    # 최신 모델
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    # 레거시 (호출 가능)
    "claude-opus-4-6",
    "claude-sonnet-4-5-20250929",
    "claude-opus-4-5-20251101",
    "claude-opus-4-1-20250805",
    # deprecated — 2026-06-15 이후 사용 불가
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
]


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
