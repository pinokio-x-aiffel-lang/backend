from __future__ import annotations

import os

from dotenv import load_dotenv

from src.llm.client import ChatClient, ChatResponse, LlmError, fetch_hcx_native
from src.llm.provider import (
    FUNCTION_CALLING_MODELS,
    GPT_MAX_COMPLETION_TOKENS_MODELS,
    GPT_RESPONSES_MODELS,
    HCX_FUNCTION_CALLING_MIN_TOKENS,
    HCX_MODELS_LOWER,
    HCX_NATIVE_MODELS,
    HCX_STRUCTURED_OUTPUT_MODELS,
    HCX_THINKING_EFFORT_MAX_TOKENS,
    HCX_THINKING_EFFORTS,
    HCX_THINKING_MODELS,
    PROVIDERS,
    ProviderConfig,
)


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise LlmError(f"환경변수 {name} 를 찾을 수 없습니다.")
    return value


class LlmCaller:
    """model_alias를 받아 적절한 provider/model로 LLM을 호출."""

    def __init__(self) -> None:
        load_dotenv()
        self._clients: dict[str, ChatClient] = {}

    def _get_client(self, model_alias: str, provider: ProviderConfig) -> ChatClient:
        if model_alias not in self._clients:
            api_key = _get_required_env(provider.api_key_env)
            self._clients[model_alias] = ChatClient(api_key=api_key, base_url=provider.base_url)
        return self._clients[model_alias]

    def chat(
        self,
        model_alias: str,
        model_name: str,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        json_structure: dict | None = None,
        function_calling: bool = False,
        thinking: bool = False,
        thinking_effort: str | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        timeout: float | None = None,
    ) -> ChatResponse:
        model_lower = model_name.lower()

        if thinking_effort is not None and thinking_effort not in HCX_THINKING_EFFORTS:
            raise LlmError(
                f"thinking_effort는 {sorted(HCX_THINKING_EFFORTS)} 중 하나여야 합니다 "
                f"(입력: {thinking_effort})"
            )
        # effort가 미지정이거나 "none"이면 추론 OFF로 간주
        thinking_on = thinking or (thinking_effort not in (None, "none"))

        # (1) HCX native 모델(HCX-005/007/DASH-002)은 Function Calling / Structured Outputs /
        #     Thinking 중 하나만 사용 가능 — 둘 이상 켜져 있으면 호출 전에 차단
        if model_lower in HCX_NATIVE_MODELS:
            structured_outputs = json_mode or json_structure is not None
            enabled = [
                name
                for name, on in (
                    ("function_calling", function_calling),
                    ("structured_outputs", structured_outputs),
                    ("thinking", thinking_on),
                )
                if on
            ]
            if len(enabled) > 1:
                raise LlmError(
                    f"[{model_name}] {', '.join(enabled)} 기능은 동시에 사용할 수 없습니다. "
                    "하나만 활성화하세요."
                )

        # (2) 기능별 미지원 모델 차단
        if function_calling and model_lower not in FUNCTION_CALLING_MODELS:
            raise LlmError("function calling을 지원하지 않는 모델입니다")

        # HCX function calling은 max_tokens 하한(1024) 제약이 있음(타 벤더는 해당 없음).
        # None이면 하한으로 자동 보정하고, 명시적으로 하한 미만이면 차단한다.
        if function_calling and model_lower in HCX_NATIVE_MODELS:
            if max_tokens is None:
                max_tokens = HCX_FUNCTION_CALLING_MIN_TOKENS
            elif max_tokens < HCX_FUNCTION_CALLING_MIN_TOKENS:
                raise LlmError(
                    f"function calling 호출 시 max_tokens는 "
                    f"{HCX_FUNCTION_CALLING_MIN_TOKENS} 이상이어야 합니다 (현재: {max_tokens})"
                )

        # structured outputs는 HCX 중 HCX-007만 지원 — 나머지 HCX는 호출 전에 차단
        if (
            json_structure is not None
            and model_lower in HCX_MODELS_LOWER
            and model_lower not in HCX_STRUCTURED_OUTPUT_MODELS
        ):
            raise LlmError("structured outputs를 지원하지 않는 모델입니다")

        if thinking_on and model_lower not in HCX_THINKING_MODELS:
            raise LlmError("thinking(추론) 모드를 지원하지 않는 모델입니다")

        if model_alias not in PROVIDERS:
            raise LlmError(f"등록되지 않은 provider: {model_alias}")

        provider = PROVIDERS[model_alias]

        if json_mode and not provider.supports_json_object:
            raise LlmError(
                f"[{model_name}] provider는 json_object 모드를 지원하지 않습니다."
            )

        if model_alias == "hyperclova" and model_name.lower() in HCX_NATIVE_MODELS:
            if provider.native_url is None:
                raise LlmError("native_url이 설정되지 않았습니다.")
            api_key = _get_required_env(provider.api_key_env)
            return fetch_hcx_native(
                api_key=api_key,
                url=f"{provider.native_url}/{model_name}",
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                json_structure=json_structure,
                tools=tools,
                tool_choice=tool_choice,
                supports_thinking=model_name.lower() in HCX_THINKING_MODELS,
                thinking_effort=thinking_effort,
                timeout=timeout or 60.0,
            )

        client = self._get_client(model_alias, provider)

        if model_alias == "openai":
            if model_name in GPT_RESPONSES_MODELS:
                return client.fetch_responses(
                    messages=messages,
                    model_name=model_name,
                    max_tokens=max_tokens,
                    tools=tools,
                    tool_choice=tool_choice,
                    timeout=timeout,
                )
            return client.fetch_chat(
                messages=messages,
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                use_max_completion_tokens=model_name in GPT_MAX_COMPLETION_TOKENS_MODELS,
                json_mode=json_mode,
                json_structure=json_structure,
                tools=tools,
                tool_choice=tool_choice,
                timeout=timeout,
            )

        return client.fetch_chat(
            messages=messages,
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            json_structure=json_structure,
            tools=tools,
            tool_choice=tool_choice,
            timeout=timeout,
        )
