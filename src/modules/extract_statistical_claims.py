from __future__ import annotations

import asyncio
import json

from src.llm.client import LlmError
from src.llm.model_presets import EXTRACT_CLAIMS
from src.observability.tracing import traced_chat
from src.prompts.prompts import EXTRACT_CLAIMS_SYSTEM, EXTRACT_CLAIMS_USER
from src.schemas.runtime import Claim, ClaimType, MasterSchema, ValueSlot

_VALID_PERIOD_TYPES: frozenset[str] = frozenset({"Y", "M", "Q", "S", "D"})

_VALID_CLAIM_TYPES: frozenset[str] = frozenset(
    ct.value for ct in ClaimType if ct is not ClaimType.NONE
)


def _to_str(val: object, fallback: str = "불명") -> str:
    """LLM이 문자열 대신 리스트나 None을 반환할 때 안전하게 문자열로 변환."""
    if isinstance(val, list):
        return ", ".join(str(v) for v in val) if val else fallback
    return str(val) if val else fallback


def _parse_claim_type(raw: object) -> ClaimType:
    """LLM 응답 claim_type 문자열 → ClaimType enum. 유효하지 않으면 NONE 반환."""
    val = str(raw).strip().lower() if raw else ""
    if val in _VALID_CLAIM_TYPES:
        return ClaimType(val)
    return ClaimType.NONE


# 필드 단위 구조 강제 — HCX responseFormat 이 필드 오타·타입 오류를 차단한다.
#
# ⚠ 스펙 신뢰 등급: 개별 키워드(type/properties/items/enum/required)는 CLOVA Studio
# Structured Outputs 공식 지원 목록에 있으나, 다음은 공식 문서에 없는 영역이다:
#   - 배열 items 안의 required (공식 예시는 평평한 객체 1단뿐 — 조합 사용례 없음)
#   - enum/required 설정 시 출력이 어떻게 보장·제약되는지 (동작 설명 자체가 문서에 없음)
# 즉 이 스키마의 효과는 스펙 보증이 아니라 260612 실측으로만 검증된 가정이며,
# HCX 모델/스펙 변경 시 회귀 테스트로 재확인해야 한다.
#
# required 는 핵심 4개만(claim_type/subject/value_raw/period_raw — 이게 없으면 하류에서
# claim 으로 못 쓰는 최소 집합): 10개 전부 강제하면 다중 claim 문장에서 HCX 가
# {"claims": []} 로 후퇴하는 현상이 결정적으로 재현됨(260612 분리 실험, 3회).
# 나머지 필드는 파서가 .get() 으로 방어(미존재 시 '불명'/None).
# 필드 의미 규칙은 프롬프트(EXTRACT_CLAIMS_SYSTEM/USER)가 담당.
CLAIMS_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sentence": {"type": "string"},
                    "claim_type": {
                        "type": "string",
                        "enum": ["absolute", "change_rate", "ratio", "distribution",
                                 "comparison", "metaphoric", "verifiable", "none"],
                    },
                    "subject": {"type": "string"},
                    "value_raw": {"type": "string"},
                    "unit": {"type": "string"},
                    "period_raw": {"type": "string"},
                    "period_type": {"type": "string", "enum": ["Y", "M", "Q", "S", "D"]},
                    "compare_period_raw": {"type": "string"},
                    "population": {"type": "string"},
                    "cited_source": {"type": "string"},
                },
                "required": ["claim_type", "subject", "value_raw", "period_raw"],
            },
        }
    },
    "required": ["claims"],
}


class ExtractStatisticalClaimsError(Exception):
    """클레임 추출 실패 — LLM 응답 파싱 오류 등."""


async def extract_statistical_claims(master_schema: MasterSchema) -> None:
    """
    [2] Extract Statistical Claims

    Input:
        master_schema.article        # [1]에서 적재된 기사

    Output:
        master_schema.claims         # list[Claim] (claim_type == NONE 포함)

    Responsibility:
        LLM으로 기사 본문에서 수치 기반 통계 주장을 추출하고 claim_type 분류.
        claim_type == NONE 인 항목도 claims에 포함 — 필터링은 분기 모듈 담당.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    if not master_schema.article:
        raise ExtractStatisticalClaimsError("master_schema.article 이 없습니다.")

    messages = [
        {"role": "system", "content": EXTRACT_CLAIMS_SYSTEM},
        {"role": "user", "content": EXTRACT_CLAIMS_USER.format(
            content=master_schema.article.content
        )},
    ]

    try:
        response = await asyncio.to_thread(
            traced_chat,
            model_alias=EXTRACT_CLAIMS.model_alias,
            model_name=EXTRACT_CLAIMS.model_name,
            messages=messages,
            max_tokens=EXTRACT_CLAIMS.max_tokens,
            temperature=EXTRACT_CLAIMS.temperature,
            json_structure=CLAIMS_SCHEMA,
            trace_name="extract_claims",
        )
    except LlmError as e:
        raise ExtractStatisticalClaimsError(f"LLM 호출 실패: {e}") from e

    try:
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0].strip()
        data = json.loads(text)
        raw_claims: list[dict] = data.get("claims", [])
    except json.JSONDecodeError as e:
        raise ExtractStatisticalClaimsError(f"LLM 응답 JSON 파싱 실패: {e}") from e

    claims: list[Claim] = []
    for idx, item in enumerate(raw_claims, start=1):
        period_type = item.get("period_type", "Y")
        if isinstance(period_type, list):
            period_type = period_type[0] if period_type else "Y"
        if period_type not in _VALID_PERIOD_TYPES:
            period_type = "Y"

        compare_raw = _to_str(item.get("compare_period_raw"), "").strip()
        compare_period_value = (
            ValueSlot(raw=compare_raw, llm_value="", is_inferred=False)
            if compare_raw and compare_raw != "불명" else None
        )

        claims.append(
            Claim(
                claim_id=f"clm-{idx:04d}",
                article_id=master_schema.article.article_id,
                sentence=_to_str(item.get("sentence"), ""),
                claim_type=_parse_claim_type(item.get("claim_type")),
                subject=_to_str(item.get("subject")),
                value=ValueSlot(raw=_to_str(item.get("value_raw")), llm_value="", is_inferred=False),
                unit=_to_str(item.get("unit")),
                aggregation="값",
                period_type=period_type,
                period_value=ValueSlot(raw=_to_str(item.get("period_raw")), llm_value="", is_inferred=False),
                compare_period_value=compare_period_value,
                population=_to_str(item.get("population")),
                cited_source=_to_str(item.get("cited_source")),
            )
        )

    master_schema.claims = claims
