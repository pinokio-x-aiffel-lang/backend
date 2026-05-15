"""LLM 클라이언트 — NCP HyperCLOVA X (OpenAI 호환 모드).

호출자는 `ChatClient.fetch_chat()` 한 메서드만 알면 됨. messages 받아서
`ChatResponse` 돌려줌. 재시도/로깅/비용 누적/대화 히스토리/JSON 파싱은
모두 호출자 책임.

기준 결정 문서: ../../docs/llm_client_spec.md
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from openai import APIError, OpenAI


DEFAULT_BASE_URL = "https://clovastudio.stream.ntruss.com/v1/openai"
DEFAULT_TIMEOUT_S = 60.0
ENV_API_KEY = "HCX_API_KEY"


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
    """NCP HyperCLOVA X 채팅 API 호출용 클라이언트.

    책임 — messages 를 받아 SDK 한 번 호출하고 ChatResponse 돌려주기.
    APIError 를 LlmError 로 wrap.

    안 함 — 재시도, 로깅, 비용 누적, 대화 히스토리, 프롬프트 작성, JSON 파싱.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        if api_key is None:
            load_dotenv()
            api_key = os.getenv(ENV_API_KEY)
            if api_key is None:
                raise LlmError(
                    f"API 키를 찾을 수 없음. 환경변수 {ENV_API_KEY} 를 설정하거나 "
                    f"api_key 인자로 전달하세요."
                )

        self.default_model = default_model
        self.timeout = timeout
        self._sdk = OpenAI(
            api_key=api_key,
            base_url=base_url or DEFAULT_BASE_URL,
            timeout=timeout,
            max_retries=0,
        )

    def fetch_chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        timeout: float | None = None,
    ) -> ChatResponse:
        """LLM 한 번 호출. 재시도 없음. 실패 시 LlmError.

        timeout 은 호출 1회 기준. 재시도가 없으므로 곧 총 시간.

        Raises:
            LlmError: SDK APIError 발생 시. 원본은 __cause__ 로 보존.
            ValueError: model 도 default_model 도 None 일 때.
        """
        used_model = model or self.default_model
        if used_model is None:
            raise ValueError("model 인자 또는 default_model 중 하나는 필수")

        kwargs: dict[str, Any] = {"messages": messages, "model": used_model}
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
