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
import httpx
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


def fetch_hcx_native(
    api_key: str,
    url: str,
    messages: list[dict],
    max_tokens: int | None = None,
    temperature: float | None = None,
    json_structure: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> ChatResponse:
    """HCX v3 네이티브 엔드포인트 직접 호출. OpenAI SDK를 거치지 않음."""
    body: dict[str, Any] = {"messages": messages}
    if max_tokens is not None:
        body["maxCompletionTokens"] = max_tokens
    if temperature is not None:
        body["temperature"] = temperature
    if json_structure is not None:
        hcx_schema = {k: v for k, v in json_structure.items() if k != "additionalProperties"}
        body["thinking"] = {"effort": "none"}  # thinking과 responseFormat은 동시 사용 불가
        body["responseFormat"] = {"type": "json", "schema": hcx_schema}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    start_s = time.time()
    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise LlmError(f"LLM 호출 실패: {e.response.status_code} {e.response.text}") from e
    except httpx.RequestError as e:
        raise LlmError(f"LLM 호출 실패: {e}") from e
    latency_s = time.time() - start_s

    data = resp.json()
    result = data.get("result", {})
    usage = result.get("usage", {})
    message = result.get("message", {})
    return ChatResponse(
        text=message.get("content", ""),
        total_tokens=usage.get("totalTokens", 0),
        prompt_tokens=usage.get("promptTokens", 0),
        completion_tokens=usage.get("completionTokens", 0),
        model=url.rsplit("/", 1)[-1],
        finish_reason=result.get("finishReason", ""),
        latency_s=latency_s,
        raw=data,
    )


class ChatClient:
    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> None:

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
        model_name: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        use_max_completion_tokens: bool = False,
        json_mode: bool = False,
        json_structure: dict | None = None,
        timeout: float | None = None,
    ) -> ChatResponse:
        """OpenAI 호환 엔드포인트 1회 호출. 재시도 없음. 실패 시 LlmError."""

        kwargs: dict[str, Any] = {"messages": messages, "model": model_name}

        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            token_key = "max_completion_tokens" if use_max_completion_tokens else "max_tokens"
            kwargs[token_key] = max_tokens
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if json_structure is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "strict": True, "schema": json_structure},
            }
        if timeout is not None:
            kwargs["timeout"] = timeout

        start_s = time.time()
        try:
            sdk_response = self._sdk.chat.completions.create(**kwargs)
        except APIError as e:
            raise LlmError(f"LLM 호출 실패: {e}") from e
        latency_s = time.time() - start_s

        choice = sdk_response.choices[0]
        return self._build_response(sdk_response, choice.message.content or "", latency_s)

    @staticmethod
    def _build_response(sdk_response: Any, text: str, latency_s: float) -> ChatResponse:
        usage = sdk_response.usage
        return ChatResponse(
            text=text,
            total_tokens=usage.total_tokens if usage else 0,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            model=sdk_response.model,
            finish_reason=sdk_response.choices[0].finish_reason or "",
            latency_s=latency_s,
            raw=sdk_response.model_dump(),
        )

    @staticmethod
    def _build_responses_response(sdk_response: Any, latency_s: float) -> ChatResponse:
        usage = sdk_response.usage
        return ChatResponse(
            text=sdk_response.output_text or "",
            total_tokens=usage.total_tokens if usage else 0,
            prompt_tokens=usage.input_tokens if usage else 0,
            completion_tokens=usage.output_tokens if usage else 0,
            model=sdk_response.model,
            finish_reason="stop",
            latency_s=latency_s,
            raw=sdk_response.model_dump(),
        )

    def fetch_responses(
        self,
        messages: list[dict],
        model_name: str,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> ChatResponse:
        """OpenAI Responses API (/v1/responses). o1-pro, gpt-5-pro 전용."""
        kwargs: dict[str, Any] = {"model": model_name, "input": messages}
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        if timeout is not None:
            kwargs["timeout"] = timeout

        start_s = time.time()
        try:
            sdk_response = self._sdk.responses.create(**kwargs)
        except APIError as e:
            raise LlmError(f"LLM 호출 실패: {e}") from e
        latency_s = time.time() - start_s

        return self._build_responses_response(sdk_response, latency_s)
