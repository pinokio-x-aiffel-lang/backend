from __future__ import annotations

import asyncio
import json

from src.llm.client import LlmError
from src.llm.llm_caller import LlmCaller
from src.llm.model_presets import EXTRACT_CLAIMS
from src.prompts.prompts import EXTRACT_CLAIMS_SYSTEM, EXTRACT_CLAIMS_USER
from src.schemas.runtime import Claim, ClaimType, MasterSchema, ValueSlot

_llm = LlmCaller()

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


CLAIMS_SCHEMA = {
    "type": "object",
    "properties": {"claims": {"type": "array", "items": {"type": "object"}}},
    "required": ["claims"],
}


class ExtractStatisticalClaimsError(Exception):
    """클레임 추출 실패 — LLM 응답 파싱 오류 등."""


async def extract_statistical_claims(master_schema: MasterSchema) -> None:
    """
    [3] Extract Statistical Claims

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
            _llm.chat,
            EXTRACT_CLAIMS.model_alias,
            EXTRACT_CLAIMS.model_name,
            messages,
            max_tokens=EXTRACT_CLAIMS.max_tokens,
            json_structure=CLAIMS_SCHEMA,
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
                compare_period_value=None,
                population=_to_str(item.get("population")),
                cited_source=_to_str(item.get("cited_source")),
            )
        )

    master_schema.claims = claims
