"""numeric.compare.compute_absolute 단위 테스트 — ABSOLUTE 직접비교 판정."""
from src.numeric.compare import compute_absolute, tolerance_abs
from src.schemas.runtime import (
    Claim,
    ClaimType,
    Evidence,
    MismatchType,
    ValueSlot,
    Verdict,
)


def _claim(llm_value, unit="%", period="2023", ctype=ClaimType.ABSOLUTE):
    return Claim(
        claim_id="c1", article_id="a1", sentence="s", claim_type=ctype,
        subject="실업률",
        value=ValueSlot(raw=llm_value, llm_value=llm_value, is_inferred=False),
        unit=unit, aggregation="값", period_type="Y",
        period_value=ValueSlot(raw=period, llm_value=period, is_inferred=False),
        population="전국", cited_source="통계청",
    )


def _ev(value, unit="%", period="2023", population_fallback=False):
    return Evidence(
        claim_id="c1", source="KOSIS", subject="실업률", unit=unit,
        period_type="Y", period=period, population="전국", value=value,
        population_fallback=population_fallback,
    )


def test_tolerance_abs():
    assert tolerance_abs("3.5") == 0.05
    assert tolerance_abs("5") == 0.5
    assert tolerance_abs("3.50") == 0.005


def test_within_tolerance_true():
    m = compute_absolute(_claim("3.5"), _ev(3.52))
    assert m.verdict is Verdict.TRUE and m.within_tolerance is True


def test_magnitude_mismatch():
    m = compute_absolute(_claim("3.5"), _ev(4.9))
    assert m.verdict is Verdict.FALSE and m.mismatch_type is MismatchType.MAGNITUDE


def test_rounding_mismatch():
    m = compute_absolute(_claim("3.5"), _ev(3.59))  # diff 0.09 ≤ 2·tol(0.1)
    assert m.verdict is Verdict.FALSE and m.mismatch_type is MismatchType.ROUNDING


def test_period_mismatch():
    m = compute_absolute(_claim("3.5", period="2023"), _ev(4.9, period="2020"))
    assert m.verdict is Verdict.FALSE and m.mismatch_type is MismatchType.PERIOD


def test_unit_incompatible_to_NEI():
    m = compute_absolute(_claim("3.5", unit="%"), _ev(1000.0, unit="명"))
    assert m.verdict is Verdict.NOT_ENOUGH_INFO and m.mismatch_type is MismatchType.UNIT


def test_percent_point_to_NEI():
    m = compute_absolute(_claim("0.4", unit="%p"), _ev(0.4, unit="%p"))
    assert m.verdict is Verdict.NOT_ENOUGH_INFO and m.mismatch_type is MismatchType.UNIT


def test_population_fallback_stays_numeric():
    # 7단계는 수치로만 T/F (폴백→M 강제 제거). 오도 여부는 8단계가 판단.
    m = compute_absolute(_claim("3.5"), _ev(3.5, population_fallback=True))
    assert m.verdict is Verdict.TRUE and "population_fallback" in (m.note or "")


def test_non_scalar_to_NEI():
    m = compute_absolute(_claim("50~100"), _ev(70.0))
    assert m.verdict is Verdict.NOT_ENOUGH_INFO


def test_unit_conversion_ok():
    # claim 100억원 vs kosis 10000백만원(=100억원) → 환산 후 일치
    m = compute_absolute(_claim("100", unit="억원"), _ev(10000.0, unit="백만원"))
    assert m.verdict is Verdict.TRUE and m.kosis_value == 100.0
