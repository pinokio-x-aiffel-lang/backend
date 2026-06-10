"""calculate_metric([7]) 단위 테스트 — claim_results 생성 + metric 산출."""
import pytest

from src.modules.calculate_metric import calculate_metric
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
    Verdict,
)


def _claim(cid, llm_value, ctype=ClaimType.ABSOLUTE, unit="%"):
    return Claim(
        claim_id=cid, article_id="a1", sentence="s", claim_type=ctype,
        subject="실업률",
        value=ValueSlot(raw=llm_value, llm_value=llm_value, is_inferred=False),
        unit=unit, aggregation="값", period_type="Y",
        period_value=ValueSlot(raw="2023", llm_value="2023", is_inferred=False),
        population="전국", cited_source="통계청",
    )


def _analysis(cid, evidence):
    return ClaimAnalysis(
        claim_id=cid,
        kosis_search=KosisSearch(api="s", query="q", params="p", hits=0, success=0, duration_ms=1),
        kosis_query=KosisQuery(api="d", tbl_id="T1", params="p", rows_returned=0, success=0, duration_ms=1),
        evidence=evidence,
    )


def _ev(cid, value):
    return Evidence(
        claim_id=cid, source="KOSIS", subject="실업률", unit="%",
        period_type="Y", period="2023", population="전국", value=value,
    )


def _master(claims, analyses):
    return MasterSchema(
        content="x", article=Article(article_id="a1", content="c"),
        claims=claims, analysis=analyses,
    )


@pytest.mark.asyncio
async def test_creates_claim_results_with_metric():
    ms = _master([_claim("c1", "3.5")], [_analysis("c1", _ev("c1", 3.52))])
    await calculate_metric(ms)

    assert ms.verifications is not None
    cr = ms.verifications.claim_results[0]
    assert cr.metric is not None
    assert cr.metric.verdict is Verdict.TRUE
    assert cr.verdict == "T"  # 상위 미러
    assert cr.claim_value == "3.5"


@pytest.mark.asyncio
async def test_no_evidence_gives_NEI():
    ms = _master([_claim("c1", "3.5")], [_analysis("c1", None)])
    await calculate_metric(ms)

    cr = ms.verifications.claim_results[0]
    assert cr.metric.verdict is Verdict.NOT_ENOUGH_INFO
    assert cr.kosis_value is None


@pytest.mark.asyncio
async def test_metaphoric_to_NEI():
    ms = _master([_claim("c1", "2.0", ctype=ClaimType.METAPHORIC)], [_analysis("c1", None)])
    await calculate_metric(ms)

    cr = ms.verifications.claim_results[0]
    assert cr.metric.verdict is Verdict.NOT_ENOUGH_INFO  # 검증 대상 아님 → NEI
