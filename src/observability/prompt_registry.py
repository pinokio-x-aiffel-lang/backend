"""Langfuse Prompt Management 레지스트리 — 코드(src/prompts/prompts.py)가 원본(source of truth).

각 LLM 호출의 (system, user) 페어에 안정적인 이름을 붙여 한곳에 모은다.
 - infra/langfuse/sync_prompts.py 가 이를 Langfuse 에 chat prompt 로 push(버전관리).
 - src/observability/tracing.py 의 traced_chat 가 generation 에 이 이름으로 prompt 를 링크.
런타임 메시지 텍스트는 항상 prompts.py 상수에서 만들어진다(접근 A). Langfuse 에 저장되는
템플릿은 표시·버전관리·링크 용도이며, USER 의 `{raw}` 등 .format 필드는 그대로 둔다
(런타임에 compile 하지 않으므로 mustache 변환 불필요).
"""
from __future__ import annotations

from src.prompts.prompts import (
    CHECK_ALIGNMENT_SYSTEM,
    CHECK_ALIGNMENT_USER,
    EXTRACT_CLAIMS_SYSTEM,
    EXTRACT_CLAIMS_USER,
    GENERATE_OPINION_SYSTEM,
    GENERATE_OPINION_USER,
    NORMALIZE_PERIOD_SYSTEM,
    NORMALIZE_PERIOD_USER,
    NORMALIZE_VALUE_SYSTEM,
    NORMALIZE_VALUE_USER,
    PREPROCESS_ARTICLE_SYSTEM,
    PREPROCESS_ARTICLE_USER,
    RANK_EVIDENCE_SYSTEM,
    RANK_EVIDENCE_USER,
    RESOLVE_AXIS_MATCH_SYSTEM,
    RESOLVE_AXIS_MATCH_USER,
)

# Langfuse prompt name → (system, user) 템플릿. 이름은 traced_chat(prompt_name=...) 과 일치.
PROMPTS: dict[str, tuple[str, str]] = {
    "preprocess_article": (PREPROCESS_ARTICLE_SYSTEM, PREPROCESS_ARTICLE_USER),
    "extract_claims": (EXTRACT_CLAIMS_SYSTEM, EXTRACT_CLAIMS_USER),
    "normalize_value": (NORMALIZE_VALUE_SYSTEM, NORMALIZE_VALUE_USER),
    "normalize_period": (NORMALIZE_PERIOD_SYSTEM, NORMALIZE_PERIOD_USER),
    "resolve_axis_match": (RESOLVE_AXIS_MATCH_SYSTEM, RESOLVE_AXIS_MATCH_USER),
    "rank_evidence": (RANK_EVIDENCE_SYSTEM, RANK_EVIDENCE_USER),
    "check_alignment": (CHECK_ALIGNMENT_SYSTEM, CHECK_ALIGNMENT_USER),
    "generate_opinion": (GENERATE_OPINION_SYSTEM, GENERATE_OPINION_USER),
}


def as_chat_prompt(name: str) -> list[dict]:
    """Langfuse chat prompt 형식(messages)으로 변환."""
    system, user = PROMPTS[name]
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
