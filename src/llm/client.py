"""LLM 클라이언트 (OpenAI 호환 모드).

호출자는 실제 api_key, base_url, model, messages를 전달한다.
ChatClient는 SDK를 통해 LLM을 1회 호출하고 ChatResponse를 반환한다.

하지 않음:
- .env 로딩
- provider 선택
- model alias 해석
- 재시도
- 로깅
- 비용 계산
- JSON 파싱
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Any
from openai import APIError, OpenAI


DEFAULT_TIMEOUT_S = 60.0


class LlmError(Exception):
    """LLM 호출 실패 시 던지는 공통 예외. 원본 예외는 __cause__ 로 보존."""


@dataclass
class ChatResponse:
    """LLM 응답 컨테이너."""

    text: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    model: str
    finish_reason: str
    latency_s: float
    raw: dict


class ChatClient:
    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> None:

        self.timeout = timeout

        sdk_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": timeout,
            "max_retries": 0,
        }

        if base_url is not None:
            sdk_kwargs["base_url"] = base_url

        self._sdk = OpenAI(**sdk_kwargs)

    def fetch_chat(
        self,
        messages: list[dict],
        model: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        timeout: float | None = None,
    ) -> ChatResponse:
        """LLM 한 번 호출. 재시도 없음. 실패 시 LlmError.

        timeout 은 호출 1회 기준. 재시도가 없으므로 곧 총 시간.

        Raises:
            LlmError: SDK APIError 발생 시. 원본은 __cause__ 로 보존.
        """

        kwargs: dict[str, Any] = {"messages": messages, "model": model}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if timeout is not None:
            kwargs["timeout"] = timeout

        start_s = time.time()
        try:
            sdk_response = self._sdk.chat.completions.create(**kwargs)
        except APIError as e:
            raise LlmError(f"LLM 호출 실패: {e}") from e
        latency_s = time.time() - start_s

        choice = sdk_response.choices[0]
        usage = sdk_response.usage
        return ChatResponse(
            text=choice.message.content or "",
            total_tokens=usage.total_tokens if usage else 0,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            model=sdk_response.model,
            finish_reason=choice.finish_reason or "",
            latency_s=latency_s,
            raw=sdk_response.model_dump(),
        )
