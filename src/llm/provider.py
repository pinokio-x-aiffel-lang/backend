from dataclasses import dataclass

CLOVASTUDIO_BASE_URL = "https://clovastudio.stream.ntruss.com/v1/openai"
# v3 native 엔드포인트 base — 실제 호출 시 뒤에 /{model_name}을 붙인다
CLOVASTUDIO_NATIVE_BASE_URL = "https://clovastudio.stream.ntruss.com/v3/chat-completions"
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
    "o3",
    "o3-mini",
    "o4-mini",
    # legacy
    "o1-pro",
    "o1",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
]

# gpt-5.x 및 o-series는 max_tokens 대신 max_completion_tokens를 사용
GPT_MAX_COMPLETION_TOKENS_MODELS: frozenset[str] = frozenset({
    "gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano",
    "gpt-5", "gpt-5-mini", "gpt-5-nano",
    "o3", "o3-mini",
    "o4-mini",
    "o1",
})

# /v1/responses 전용 — OpenAI Responses API
GPT_RESPONSES_MODELS: frozenset[str] = frozenset({
    "gpt-5.5-pro",
    "gpt-5.4-pro",
    "gpt-5-pro",
    "o1-pro",
    # reasoning(thinking) + tool calling 동시 지원 — Responses API 경유
    "gpt-5.4-mini",
    "gpt-5.4",
    "gpt-5.5",
})

# 출처: https://guide.ncloud-docs.com/docs/clovastudio-model (2026-05 기준)
# context_window: 입력+출력 합산 한도 / max_output_tokens: 출력 단독 한도
# HCX-DASH-001은 context_window(3,500)가 병목 — max_tokens는 입력 길이를 고려해 설정해야 함
HCX_MODEL_INFO: dict[str, dict] = {
    "HCX-007":      {"context_window": 128_000, "max_output_tokens": 32_768},
    "HCX-005":      {"context_window": 128_000, "max_output_tokens":  4_096},
    "HCX-DASH-002": {"context_window":  32_000, "max_output_tokens":  4_096},
    "HCX-003":      {"context_window":   7_600, "max_output_tokens":  4_096},
    "HCX-DASH-001": {"context_window":   3_500, "max_output_tokens":  4_096},
}
HCX_MODELS: list[str] = list(HCX_MODEL_INFO)
HCX_MODELS_LOWER: frozenset[str] = frozenset(m.lower() for m in HCX_MODELS)
# v3 native endpoint를 사용하는 HCX 모델 (소문자 비교용).
# 이 3종은 동시에 (1) v3 native 호출 대상이며, (2) function calling을 지원하고,
# (3) 이미지 입력/튜닝/Function Calling/Structured Outputs/Thinking 중 한 번에 하나만
# 사용 가능하다(동시 사용 불가).
HCX_NATIVE_MODELS: frozenset[str] = frozenset({"hcx-005", "hcx-007", "hcx-dash-002"})
# thinking 파라미터를 지원하는 모델 (나머지 HCX는 thinking 전송 시 400 에러, 소문자 비교용)
HCX_THINKING_MODELS: frozenset[str] = frozenset({"hcx-007"})
# thinking.effort 유효값 (실호출 검증: "mid"는 400, "medium"이 정상)
HCX_THINKING_EFFORTS: frozenset[str] = frozenset({"none", "low", "medium", "high"})
# effort가 높을수록 추론이 토큰을 더 소비 → max_tokens 미지정 시 effort별 기본 budget.
# (실측 completion_tokens: none~245 / low~636 / medium~1216 / high~1230, 여유 포함)
HCX_THINKING_EFFORT_MAX_TOKENS: dict[str, int] = {"low": 2048, "medium": 4096, "high": 8192}
# structured outputs를 지원하는 HCX 모델 (소문자 비교용).
# HCX-007만 지원하며, 나머지 HCX는 responseFormat 전송 시 400(native) 또는
# json_schema가 무시됨(v1 compat) → 호출 전에 차단한다.
HCX_STRUCTURED_OUTPUT_MODELS: frozenset[str] = frozenset({"hcx-007"})
# HCX function calling 호출 시 max_tokens 하한 (미만이면 tools와 호환 안 됨 → 400)
HCX_FUNCTION_CALLING_MIN_TOKENS = 1024

# 출처: https://ai.google.dev/gemini-api/docs/models (2026-05 기준, 텍스트 생성 + 무료 tier)
GEMINI_MODELS = [
    # Gemini 3.x (stable)
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    # Gemini 3.x (preview)
    "gemini-3-flash-preview",
    # Gemini 2.5 (stable)
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
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
]

# json_schema(Structured Outputs) 미지원 모델
NO_STRUCTURED_OUTPUT_MODELS: frozenset[str] = frozenset({
    # OpenAI legacy — gpt-4o 이전 모델
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
    # Anthropic Claude — 구조화 출력 미지원
    *CLAUDE_MODELS,
})

# function calling(tool use)을 지원하는 모델 (소문자 비교용). 실호출로 검증함.
# - HCX: HCX_NATIVE_MODELS(005/007/DASH-002)만 지원
# - GPT/Gemini/Claude: 전 모델 지원 (GPT_RESPONSES_MODELS 포함 — fetch_responses가
#   tools를 Responses 포맷으로 변환해 전송하며 4종 모두 실호출로 tool_calls 확인됨)
FUNCTION_CALLING_MODELS: frozenset[str] = (
    HCX_NATIVE_MODELS
    | frozenset(m.lower() for m in GPT_MODELS)
    | frozenset(m.lower() for m in GEMINI_MODELS)
    | frozenset(m.lower() for m in CLAUDE_MODELS)
)


@dataclass(frozen=True)
class ProviderConfig:
    api_key_env: str
    supports_json_object: bool
    supports_structured_output: bool
    base_url: str | None = None
    native_url: str | None = None  # v3 native endpoint base (httpx 직접 호출용, /{model_name} 추가)


PROVIDERS: dict[str, ProviderConfig] = {
    "openai": ProviderConfig(
        api_key_env="OPENAI_API_KEY",
        supports_json_object=True,
        supports_structured_output=True,
    ),
    "hyperclova": ProviderConfig(
        api_key_env="CLOVASTUDIO_API_KEY",
        supports_json_object=False,   # v1/openai compat endpoint rejects response_format
        supports_structured_output=True,
        base_url=CLOVASTUDIO_BASE_URL,
        native_url=CLOVASTUDIO_NATIVE_BASE_URL,
    ),
    "claude": ProviderConfig(
        api_key_env="ANTHROPIC_API_KEY",
        supports_json_object=False,
        supports_structured_output=False,
        base_url=ANTHROPIC_BASE_URL,
    ),
    "gemini": ProviderConfig(
        api_key_env="GEMINI_API_KEY",
        supports_json_object=True,
        supports_structured_output=True,
        base_url=GEMINI_BASE_URL,
    ),
}
