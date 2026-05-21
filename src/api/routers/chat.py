"""채팅 라우터.

POST /v1/chat       — 단일/멀티턴 (stateless, messages 전체 입력)
GET  /v1/providers  — 사용 가능한 provider 목록 (디버깅용)
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import get_logger, get_registry
from src.api.logging_utils import JsonlLogger
from src.api.providers.base import ChatProvider
from src.api.schemas import (
    ChatRequest,
    ChatResponseBody,
    ProvidersResponse,
    Usage,
)
from src.llm import LlmError

router = APIRouter(prefix="/v1", tags=["chat"])


@router.get("/providers", response_model=ProvidersResponse)
def list_providers(
    registry: dict[str, ChatProvider] = Depends(get_registry),
) -> ProvidersResponse:
    return ProvidersResponse(providers=sorted(registry))


@router.post("/chat", response_model=ChatResponseBody)
async def create_chat(
    req: ChatRequest,
    registry: dict[str, ChatProvider] = Depends(get_registry),
    logger: JsonlLogger = Depends(get_logger),
) -> ChatResponseBody:
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    provider = registry.get(req.provider)
    if provider is None:
        # 잘못된 provider → 통일 에러(글로벌 핸들러가 스키마로 변환)
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unknown_provider",
                "message": (
                    f"provider '{req.provider}' 없음. "
                    f"가능: {sorted(registry)}"
                ),
            },
        )

    messages = [m.model_dump() for m in req.messages]
    try:
        result = await provider.chat(
            messages=messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
    except LlmError as e:
        logger.log(
            {
                "request_id": request_id,
                "provider": req.provider,
                "messages": messages,
                "error": str(e),
            }
        )
        raise HTTPException(
            status_code=502,
            detail={"code": "upstream_error", "message": str(e)},
        ) from e

    body = ChatResponseBody(
        provider=req.provider,
        content=result.text,
        usage=Usage(
            input_tokens=result.prompt_tokens,
            output_tokens=result.completion_tokens,
        ),
        latency_ms=int(result.latency_s * 1000),
        request_id=request_id,
    )

    logger.log(
        {
            "request_id": request_id,
            "provider": req.provider,
            "messages": messages,
            "response": body.model_dump(),
        }
    )
    return body
