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
    tool_calls: list[dict] | None = None


def fetch_hcx_native(
    api_key: str,
    url: str,
    messages: list[dict],
    max_tokens: int | None = None,
    temperature: float | None = None,
    json_structure: dict | None = None,
    tools: list[dict] | None = None,
    tool_choice: str | dict | None = None,
    supports_thinking: bool = True,
    thinking_effort: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> ChatResponse:
    """HCX v3 네이티브 엔드포인트 직접 호출. OpenAI SDK를 거치지 않음.

    supports_thinking=False인 모델(HCX-005, HCX-DASH-002)은 thinking 파라미터를
    아예 전송하지 않는다(전송 시 400 에러).
    thinking_effort(none/low/medium/high)는 tools/responseFormat이 없는 일반 호출에서만
    적용된다(둘과는 동시 사용 불가라 그 경우 강제로 effort:none을 보낸다).
    """
    body: dict[str, Any] = {"messages": messages}
    if max_tokens is not None:
        body["maxCompletionTokens"] = max_tokens
    if temperature is not None:
        body["temperature"] = temperature
    if json_structure is not None:
        hcx_schema = {k: v for k, v in json_structure.items() if k != "additionalProperties"}
        if supports_thinking:  # thinking과 responseFormat은 동시 사용 불가 → 명시적으로 끔
            body["thinking"] = {"effort": "none"}
        body["responseFormat"] = {"type": "json", "schema": hcx_schema}
    elif supports_thinking and thinking_effort is not None:  # 일반 호출의 추론 강도 지정
        body["thinking"] = {"effort": thinking_effort}
    if tools is not None:
        body["tools"] = tools
        if supports_thinking:  # thinking과 function calling은 동시 사용 불가 → 명시적으로 끔
            body["thinking"] = {"effort": "none"}
        if tool_choice is not None:
            body["toolChoice"] = tool_choice  # native: "auto" | "none" | {type, function}

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
        tool_calls=message.get("toolCalls") or None,
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
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        timeout: float | None = None,
    ) -> ChatResponse:
        """OpenAI 호환 엔드포인트 1회 호출. 재시도 없음. 실패 시 LlmError."""

        kwargs: dict[str, Any] = {"messages": messages, "model": model_name}

        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            token_key = "max_completion_tokens" if use_max_completion_tokens else "max_tokens"
            kwargs[token_key] = max_tokens
        if tools is not None:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
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
        message = sdk_response.choices[0].message
        raw_tool_calls = getattr(message, "tool_calls", None)
        tool_calls = (
            [tc.model_dump() for tc in raw_tool_calls] if raw_tool_calls else None
        )
        return ChatResponse(
            text=text,
            total_tokens=usage.total_tokens if usage else 0,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            model=sdk_response.model,
            finish_reason=sdk_response.choices[0].finish_reason or "",
            latency_s=latency_s,
            raw=sdk_response.model_dump(),
            tool_calls=tool_calls,
        )

    @staticmethod
    def _build_responses_response(sdk_response: Any, latency_s: float) -> ChatResponse:
        usage = sdk_response.usage
        # Responses API의 function_call 출력 아이템을 chat completions tool_calls 형태로 변환
        tool_calls = [
            {
                "id": getattr(o, "call_id", None) or getattr(o, "id", ""),
                "type": "function",
                "function": {"name": o.name, "arguments": o.arguments},
            }
            for o in (sdk_response.output or [])
            if getattr(o, "type", None) == "function_call"
        ] or None
        return ChatResponse(
            text=sdk_response.output_text or "",
            total_tokens=usage.total_tokens if usage else 0,
            prompt_tokens=usage.input_tokens if usage else 0,
            completion_tokens=usage.output_tokens if usage else 0,
            model=sdk_response.model,
            finish_reason="tool_calls" if tool_calls else "stop",
            latency_s=latency_s,
            raw=sdk_response.model_dump(),
            tool_calls=tool_calls,
        )

    def fetch_responses(
        self,
        messages: list[dict],
        model_name: str,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        timeout: float | None = None,
    ) -> ChatResponse:
        """OpenAI Responses API (/v1/responses). gpt-5-pro, o1-pro 등 전용.

        tools/tool_choice는 chat completions 포맷으로 받아 Responses 포맷으로 변환한다.
        (Responses는 function 필드를 중첩하지 않고 평탄화한다.)
        """
        kwargs: dict[str, Any] = {"model": model_name, "input": messages}
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        if tools is not None:
            responses_tools = []
            for t in tools:
                fn = t.get("function", t)
                spec: dict[str, Any] = {"type": "function", "name": fn["name"]}
                if fn.get("description") is not None:
                    spec["description"] = fn["description"]
                if fn.get("parameters") is not None:
                    spec["parameters"] = fn["parameters"]
                responses_tools.append(spec)
            kwargs["tools"] = responses_tools
        if tool_choice is not None:
            if isinstance(tool_choice, dict) and "function" in tool_choice:
                kwargs["tool_choice"] = {
                    "type": "function",
                    "name": tool_choice["function"]["name"],
                }
            else:
                kwargs["tool_choice"] = tool_choice
        if timeout is not None:
            kwargs["timeout"] = timeout

        start_s = time.time()
        try:
            sdk_response = self._sdk.responses.create(**kwargs)
        except APIError as e:
            raise LlmError(f"LLM 호출 실패: {e}") from e
        latency_s = time.time() - start_s

        return self._build_responses_response(sdk_response, latency_s)
