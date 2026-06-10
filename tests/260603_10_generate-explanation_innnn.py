"""generate_explanation 모듈 단위 테스트.

대상 모듈: generate_explanation
작성자: innnn <innnn712@gmail.com>
작성일: 2026-06-03
"""
import pytest

from src.modules.generate_explanation import generate_explanation
from src.schemas.runtime import (
    Claim,
    ClaimType,
    ClaimResult,
    Evidence,
    MasterSchema,
    VerificationSummary,
    Verifications,
    ValueSlot,
)


# ------------------------------------------------------------------ #
# 픽스처 헬퍼
# ------------------------------------------------------------------ #
def _make_evidence(claim_id: str = "c01") -> Evidence:
    return Evidence(
        evidence_id="ev001",
        claim_id=claim_id,
        source="KOSIS",
        subject="합계출산율",
        value=0.72,
        unit="명",
        period_type="Y",
        period="2024",
        population="전국",
        kosis_org_id="101",
        kosis_tbl_id="DT_1B8000F",
        table_name="출생아수, 합계출산율, 자연증가 등",
        kosis_item_id="T20",
        url="https://kosis.kr",
        last_updated="2025-02-26",
        retrieved_at="2026-05-11T09:12:03",
    )


def _make_claim(claim_id: str = "c01", period_type: str = "Y", period: str = "2024") -> Claim:
    return Claim(
        claim_id=claim_id,
        article_id="art-001",
        sentence="테스트 문장",
        claim_type=ClaimType.ABSOLUTE,
        subject="합계출산율",
        value=ValueSlot(**{"Original_table": "0.72", "LLM_Metrics": "0.72", "Inferred": False}),
        unit="명",
        aggregation="비율",
        period_type=period_type,
        period_value=ValueSlot(**{"Original_table": period, "LLM_Metrics": period, "Inferred": False}),
        population="전국",
        cited_source="통계청",
    )


def _make_record(
    verdict: str,
    claim_value: str = "0.72",
    kosis_value: str = "0.72",
    mismatch_type: str | None = None,
    with_evidence: bool = True,
    with_claim: bool = True,
    period_type: str = "Y",
    period: str = "2024",
) -> MasterSchema:
    evidence = [_make_evidence()] if with_evidence else []
    claim_result = ClaimResult(
        claim_id="c01",
        verdict=verdict,
        claim_value=claim_value,
        kosis_value=kosis_value,
        explanation="",
        confidence=0.9,
        llm_model="test",
        mismatch_type=mismatch_type,
        evidence=evidence,
    )
    claims = [_make_claim(period_type=period_type, period=period)] if with_claim else []
    return MasterSchema(
        claims=claims,
        verifications=Verifications(
            summary=VerificationSummary(
                total_claims=1,
                overall_verdict=verdict,
                average_confidence=0.9,
            ),
            claim_results=[claim_result],
        ),
    )


# ------------------------------------------------------------------ #
# verdict별 템플릿 출력
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_verdict_t_contains_일치():
    record = _make_record("T")
    await generate_explanation(record)
    exp = record.verifications.claim_results[0].explanation
    assert "일치" in exp
    assert "0.72명" in exp
    assert "2024년" in exp


@pytest.mark.asyncio
async def test_verdict_f_contains_다릅니다():
    record = _make_record("F", claim_value="0.72", kosis_value="0.80")
    await generate_explanation(record)
    exp = record.verifications.claim_results[0].explanation
    assert "다릅니다" in exp
    assert "0.80명" in exp


@pytest.mark.asyncio
async def test_verdict_f_with_mismatch_type():
    record = _make_record("F", claim_value="0.72", kosis_value="0.80", mismatch_type="수치오류")
    await generate_explanation(record)
    exp = record.verifications.claim_results[0].explanation
    assert "수치오류" in exp


@pytest.mark.asyncio
async def test_verdict_m_contains_부분():
    record = _make_record("M", claim_value="0.72", kosis_value="0.70")
    await generate_explanation(record)
    exp = record.verifications.claim_results[0].explanation
    assert "부분" in exp


@pytest.mark.asyncio
async def test_verdict_nei_contains_검증불가():
    record = _make_record("NEI")
    await generate_explanation(record)
    exp = record.verifications.claim_results[0].explanation
    assert "검증할 수 없습니다" in exp


@pytest.mark.asyncio
async def test_verdict_unverified_contains_검증불가():
    record = _make_record("UNVERIFIED")
    await generate_explanation(record)
    exp = record.verifications.claim_results[0].explanation
    assert "검증할 수 없습니다" in exp


# ------------------------------------------------------------------ #
# 엣지 케이스
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_no_verifications_is_noop():
    record = MasterSchema()
    await generate_explanation(record)  # raise 없이 반환해야 함


@pytest.mark.asyncio
async def test_no_evidence_no_source_note():
    record = _make_record("T", with_evidence=False)
    await generate_explanation(record)
    exp = record.verifications.claim_results[0].explanation
    assert "출처" not in exp


@pytest.mark.asyncio
async def test_source_note_included_when_evidence_present():
    record = _make_record("T", with_evidence=True)
    await generate_explanation(record)
    exp = record.verifications.claim_results[0].explanation
    assert "출처" in exp


@pytest.mark.asyncio
async def test_claim_not_found_uses_fallback():
    """claim_id 매핑 실패 시 기본값으로 대체되어야 한다."""
    record = _make_record("T", with_claim=False)
    await generate_explanation(record)
    exp = record.verifications.claim_results[0].explanation
    assert "해당 지표" in exp


@pytest.mark.asyncio
async def test_period_type_m_formats_month():
    record = _make_record("T", period_type="M", period="202403")
    await generate_explanation(record)
    exp = record.verifications.claim_results[0].explanation
    assert "2024년" in exp
    assert "3월" in exp


@pytest.mark.asyncio
async def test_ambiguous_period_omitted():
    """형식 불명확한 period는 설명에 그대로 노출되지 않아야 한다."""
    record = _make_record("T", period_type="Y", period="(앞 문장에서 추론)")
    await generate_explanation(record)
    exp = record.verifications.claim_results[0].explanation
    assert "앞 문장에서 추론" not in exp
