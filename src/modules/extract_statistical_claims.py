from __future__ import annotations

import asyncio
import json
import re

from src.llm.client import LlmError
from src.llm.model_presets import EXTRACT_CLAIMS
from src.modules.preprocess_article import atomize_sentences, clean_and_split
from src.observability.tracing import traced_chat
from src.prompts.prompts import EXTRACT_CLAIMS_SYSTEM, EXTRACT_CLAIMS_USER
from src.schemas.runtime import Claim, ClaimType, MasterSchema, ValueSlot

_VALID_PERIOD_TYPES: frozenset[str] = frozenset({"Y", "M", "Q", "S", "D"})

# 통계 후보 문장 필터: 아라비아 숫자, %·퍼센트·포인트, 비유적 수치 표현(두 배·절반 등).
# 재현율 우선 — 과포함은 LLM 토큰 낭비에 그치지만 누락은 claim 유실로 이어진다.
_RE_STAT_CANDIDATE = re.compile(
    r"[0-9０-９]"
    r"|%|퍼센트|포인트"
    r"|절반|반토막|갑절|곱절"
    r"|(?:두|세|네|다섯|여섯|일곱|여덟|아홉|열|스무|몇)\s?배"
)


def _filter_stat_candidates(sentences: list[str]) -> list[str]:
    """통계 주장 후보가 될 만한 문장만 남긴다 (원자화 LLM 호출 전 비용 절감)."""
    return [s for s in sentences if _RE_STAT_CANDIDATE.search(s)]

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
        master_schema.sentences      # list[str] (필터·원자화된 검증 단위 문장)
        master_schema.claims         # list[Claim] (claim_type == NONE 포함)

    Responsibility:
        내부 3단계로 기사 본문에서 수치 기반 통계 주장을 추출하고 claim_type 분류.
          [a] 문장 필터 — 정제·문장분리(규칙) 후 통계 후보 문장만 선별
          [b] 전처리   — preprocess_article 의 원자 문장화(HCX-005) 호출
          [c] 추출     — 원자 문장들에서 LLM 으로 claim 추출·스키마 적재
        claim_type == NONE 인 항목도 claims에 포함 — 필터링은 분기 모듈 담당.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    if not master_schema.article:
        raise ExtractStatisticalClaimsError("master_schema.article 이 없습니다.")

    # [a] 문장 필터: 정제 + 문장 분리(규칙) 후 통계 후보 문장만 선별
    sentences = clean_and_split(master_schema.article.content)
    candidates = _filter_stat_candidates(sentences)
    if not candidates:
        # 수치 문장이 전혀 없으면 통계 주장도 없다 — LLM 호출 없이 종료
        master_schema.sentences = []
        master_schema.claims = []
        return

    # [b] 전처리: 복합 문장 → 검증 단위 원자 문장 (HCX-005)
    atomic_sentences = await atomize_sentences(candidates)
    master_schema.sentences = atomic_sentences

    # [c] 추출: 원자 문장 목록에서 claim 추출
    messages = [
        {"role": "system", "content": EXTRACT_CLAIMS_SYSTEM},
        {"role": "user", "content": EXTRACT_CLAIMS_USER.format(
            content="\n".join(atomic_sentences)
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
