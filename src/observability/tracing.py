"""LLM 호출 Langfuse 트레이싱 래퍼.

기존 src/llm/* 코드(특히 수정 금지인 client.py)를 건드리지 않고, LlmCaller.chat()
을 Langfuse "generation" 관측으로 감싼다.

자격(LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST)은 Langfuse SDK 가 환경변수에서 읽는다
(Infisical 주입). 자격이 없으면 SDK 가 비활성화되어 traced_chat 은 트레이싱 없이
그냥 LlmCaller.chat() 결과를 반환한다(graceful no-op).

사용:
    from src.observability import traced_chat
    resp = traced_chat(
        model_alias="hyperclova",
        model_name="HCX-005",
        messages=[...],
        max_tokens=64,
    )

실행(트레이싱 활성):
    infisical run --env dev --path /LangFuse -- uv run python your_script.py
"""
from __future__ import annotations

from typing import Any, Optional

from langfuse import get_client

from src.llm.client import ChatResponse
from src.llm.llm_caller import LlmCaller

# LlmCaller 는 생성 비용(load_dotenv 등)이 있으니 모듈 단위로 1회 생성·재사용.
_caller: Optional[LlmCaller] = None

# Langfuse Prompt Management 링크에 쓸 라벨(sync_prompts 가 다는 것과 동일).
PROMPT_LABEL = "production"


def _get_caller() -> LlmCaller:
    global _caller
    if _caller is None:
        _caller = LlmCaller()
    return _caller


def _linked_prompt(lf: Any, prompt_name: Optional[str]) -> Any:
    """generation 링크용 등록 prompt 객체. 미등록·비활성·오류 시 None(graceful no-op).

    get_prompt 는 SDK 가 클라이언트측에서 캐시(cache_ttl_seconds)하므로 호출당 네트워크
    비용이 거의 없다. 키 미주입(비활성)이거나 아직 sync 안 된 프롬프트면 None.
    """
    if not prompt_name:
        return None
    try:
        return lf.get_prompt(
            prompt_name,
            label=PROMPT_LABEL,
            type="chat",
            cache_ttl_seconds=300,
            fallback=None,
        )
    except Exception:
        return None


def traced_chat(
    *,
    model_alias: str,
    model_name: str,
    messages: list[dict],
    trace_name: Optional[str] = None,
    prompt_name: Optional[str] = None,
    **kwargs: Any,
) -> ChatResponse:
    """LlmCaller.chat() 호출을 Langfuse generation 으로 감싼다.

    입력(messages)·출력(text)·모델·토큰·지연을 자동 기록한다. kwargs 는
    LlmCaller.chat 으로 그대로 전달된다(temperature, max_tokens, json_mode 등).

    prompt_name 을 주면 Langfuse Prompt Management 의 동명 프롬프트(production 라벨)를
    이 generation 에 링크한다(버전별 지표·계보). prompt_registry.PROMPTS 의 키와 일치해야
    하며, 텍스트 자체는 항상 호출부가 만든 messages 를 쓴다(코드가 원본).
    """
    lf = get_client()

    model_parameters = {
        k: v
        for k, v in {
            "temperature": kwargs.get("temperature"),
            "max_tokens": kwargs.get("max_tokens"),
            "thinking_effort": kwargs.get("thinking_effort"),
        }.items()
        if v is not None
    }

    with lf.start_as_current_observation(
        as_type="generation",
        name=trace_name or f"{model_alias}:{model_name}",
        model=model_name,
        input=messages,
        model_parameters=model_parameters or None,
        prompt=_linked_prompt(lf, prompt_name),
    ) as gen:
        resp = _get_caller().chat(
            model_alias=model_alias,
            model_name=model_name,
            messages=messages,
            **kwargs,
        )
        gen.update(
            output=resp.text,
            usage_details={
                "input": resp.prompt_tokens,
                "output": resp.completion_tokens,
                "total": resp.total_tokens,
            },
            metadata={
                "latency_s": round(resp.latency_s, 3),
                "finish_reason": resp.finish_reason,
                "resolved_model": resp.model,
            },
        )
        return resp
