"""ABSOLUTE 수치 비교 — 주장값 ↔ KOSIS 공식값 직접 비교. [파이프라인 7 / Numeric Layer]

유효숫자(반올림) 기반 허용오차로 일치(T)/불일치(F)를 판정하고, 불일치 사유를
mismatch_type 으로 분류한다. 그룹연산(change_rate/ratio 등)은 다루지 않는다(Phase 2).
"""
from __future__ import annotations

import re

from src.numeric.units import align_value
from src.numeric.value import ValueKind, parse_claim_value
from src.schemas.runtime import (
    Claim,
    Evidence,
    MetricResult,
    MismatchType,
    Verdict,
)


def _decimal_places(s: str) -> int:
    """표기의 유효 소수 자릿수. 끝자리 0은 정밀도로 치지 않는다(3.0==3).

    '3.5'→1, '5'→0, '3.0'→0, '3.50'→1, '3.10'→1, '3.00'→0.
    → tolerance_abs 가 '3.0' 을 정수 3(±0.5)으로 보게 해, '3%대'(3.0) 가 3.1% 를 허용.
    """
    m = re.search(r"\.(\d+)", s or "")
    return len(m.group(1).rstrip("0")) if m else 0


def tolerance_abs(claim_repr: str) -> float:
    """유효숫자(반올림) 허용오차 = 마지막 표기 자리의 ±0.5.

    '3.5'→0.05, '5.9'→0.05, '5'→0.5, '3.50'→0.005.
    """
    return 0.5 * (10 ** (-_decimal_places(claim_repr)))


def _year(s: str | None) -> str | None:
    m = re.match(r"(\d{4})", (s or "").strip())
    return m.group(1) if m else None


def _classify_mismatch(
    claim: Claim, evidence: Evidence, abs_diff: float, tol: float
) -> MismatchType:
    """verdict=F 사유 분류. 기간(연도)부터 보고, 아니면 초과 폭으로."""
    cy, ey = _year(claim.period_value.llm_value), _year(evidence.period)
    if cy and ey and cy != ey:
        return MismatchType.PERIOD
    return MismatchType.ROUNDING if abs_diff <= 2 * tol else MismatchType.MAGNITUDE


def compute_absolute(claim: Claim, evidence: Evidence) -> MetricResult:
    """단일 셀 직접비교. evidence.value 가 있는 ABSOLUTE/VERIFIABLE claim 전용.

    호출 전제: evidence is not None and evidence.value is not None.
    """
    operation = claim.claim_type.value
    parsed = parse_claim_value(claim.value.llm_value)
    kosis_raw = evidence.value

    # 비스칼라(범위/비/방향만/파싱불가)는 단일 절대비교 불가 → 정보부족(NEI)
    if parsed.kind != ValueKind.SCALAR or parsed.number is None:
        return MetricResult(
            operation=operation,
            claim_value=parsed.number,
            kosis_value=kosis_raw,
            verdict=Verdict.NOT_ENOUGH_INFO,
            note=f"단일 절대비교 불가(value kind={parsed.kind.value})",
        )

    claim_value = parsed.number

    aligned, status = align_value(kosis_raw, evidence.unit, claim.unit)
    if status in ("incompatible", "unknown_unit", "non_absolute"):
        return MetricResult(
            operation=operation,
            claim_value=claim_value,
            kosis_value=kosis_raw,
            verdict=Verdict.NOT_ENOUGH_INFO,
            mismatch_type=MismatchType.UNIT,
            note=f"단위 비교불가({status}): claim={claim.unit!r} kosis={evidence.unit!r}",
        )

    notes: list[str] = []
    if status == "ok":
        notes.append(f"단위환산 {evidence.unit}→{claim.unit}")

    abs_diff = abs(claim_value - aligned)
    rel_diff = abs_diff / abs(aligned) if aligned != 0 else None
    if aligned == 0:
        notes.append("기준값 0 — rel_diff 산출 불가")

    tol = tolerance_abs(claim.value.llm_value)
    within = abs_diff <= tol

    verdict = Verdict.TRUE if within else Verdict.FALSE
    mismatch = None if within else _classify_mismatch(claim, evidence, abs_diff, tol)

    # 모집단 폴백 — '전체(합계)' 대체값과 비교. 7단계는 수치로만 T/F 를 내고,
    # 요청 집단↔전체 오도 여부는 [8] check_alignment 가 (T인 경우) 판단한다.
    if evidence.population_fallback:
        notes.append("population_fallback: 요청 집단 대신 전체(합계)값과 비교 — [8] 정합성 확인 대상")

    return MetricResult(
        operation=operation,
        claim_value=claim_value,
        kosis_value=aligned,
        rel_diff=rel_diff,
        within_tolerance=within,
        verdict=verdict,
        mismatch_type=mismatch,
        note="; ".join(notes) or None,
    )
