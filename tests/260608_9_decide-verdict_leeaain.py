"""decide_verdict 모듈 단위 테스트.

KOSIS evidence 유무에 따라 kosis_value 가 실제값/None 으로 갈리는지,
하드코딩 더미값(0.72)이 더 이상 새지 않는지 검증한다.

대상 모듈: decide_verdict
작성자: leeaain2027 <leeaain2027@gmail.com>
작성일: 2026-06-08
"""
import pytest

from src.modules.decide_verdict import decide_verdict
from src.modules.generate_explanation import generate_explanation
from src.schemas.runtime import (
    Article,
    Claim,
    ClaimAnalysis,
    ClaimType,
    Evidence,
    KosisQuery,
    KosisSearch,
    MasterSchema,
    ValueSlot,
)


# ------------------------------------------------------------------ #
# 픽스처 헬퍼
# ------------------------------------------------------------------ #
def _make_claim() -> Claim:
    return Claim(
        claim_id="clm-0001",
        article_id="a1",
        sentence="2024년 합계출산율은 0.72명이다.",
        claim_type=ClaimType.ABSOLUTE,
        subject="합계출산율",
        value=ValueSlot(raw="0.72명", llm_value="0.72", is_inferred=False),
        unit="명",
        aggregation="값",
        period_type="Y",
        period_value=ValueSlot(raw="2024년", llm_value="2024", is_inferred=False),
        population="전국",
        cited_source="통계청",
    )


def _make_analysis(evidence: Evidence | None) -> ClaimAnalysis:
    return ClaimAnalysis(
        claim_id="clm-0001",
        kosis_search=KosisSearch(api="s", query="q", params="p", hits=0, success=0, duration_ms=1),
        kosis_query=KosisQuery(api="d", tbl_id="T1", params="p", rows_returned=0, success=0, duration_ms=1),
        evidences=[evidence] if evidence is not None else [],
    )


def _make_master(analysis: list[ClaimAnalysis]) -> MasterSchema:
    return MasterSchema(
        content="x",
        article=Article(article_id="a1", content="c"),
        claims=[_make_claim()],
        analysis=analysis,
    )


# ------------------------------------------------------------------ #
# 테스트
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_kosis_value_none_when_no_analysis():
    """analysis 가 비어 있으면(=KOSIS 조회 전/실패) kosis_value 는 None."""
    ms = _make_master([])
    await decide_verdict(ms)
    result = ms.verifications.claim_results[0]
    assert result.kosis_value is None


@pytest.mark.asyncio
async def test_kosis_value_none_when_evidence_missing():
    """analysis 는 있으나 evidence=None 이면 kosis_value 는 None (더미 0.72 금지)."""
    ms = _make_master([_make_analysis(None)])
    await decide_verdict(ms)
    result = ms.verifications.claim_results[0]
    assert result.kosis_value is None


@pytest.mark.asyncio
async def test_kosis_value_from_real_evidence():
    """evidence.value 가 있으면 그 실제 KOSIS 값을 문자열로 노출."""
    evidence = Evidence(
        claim_id="clm-0001",
        source="KOSIS",
        subject="합계출산율",
        unit="명",
        period_type="Y",
        period="2024",
        population="전국",
        value=0.72,
    )
    ms = _make_master([_make_analysis(evidence)])
    await decide_verdict(ms)
    result = ms.verifications.claim_results[0]
    assert result.kosis_value == "0.72"


@pytest.mark.asyncio
async def test_explanation_no_none_leak_when_kosis_value_none():
    """kosis_value=None 일 때 generate_explanation 설명에 'None' 이 새지 않는다."""
    ms = _make_master([])
    await decide_verdict(ms)
    await generate_explanation(ms)
    result = ms.verifications.claim_results[0]
    assert "None" not in result.explanation
