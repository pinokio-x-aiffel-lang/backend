"""Pydantic 요청/응답 모델 (OpenAI 호환 형태).

세션은 stateless — 클라이언트가 매 요청마다 messages 전체를 보낸다.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    provider: str = Field(..., description="registry 의 provider 이름 (예: hcx-005)")
    messages: list[Message] = Field(..., min_length=1)
    temperature: float | None = None
    max_tokens: int | None = None
    # 기존 ChatClient.fetch_chat 는 top_p 를 받지 않는다. 호환을 위해
    # 스키마에는 두지만 하위 클라이언트로 전달하지 않는다(무시).
    top_p: float | None = None


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int


class ChatResponseBody(BaseModel):
    provider: str
    content: str
    usage: Usage
    latency_ms: int
    request_id: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ProvidersResponse(BaseModel):
    providers: list[str]
