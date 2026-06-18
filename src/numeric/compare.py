"""수치 비교 — 주장값 ↔ KOSIS 공식값. [파이프라인 7 / Numeric Layer]

유효숫자(반올림) 기반 허용오차로 일치(T)/불일치(F)를 판정하고, 불일치 사유를
mismatch_type 으로 분류한다.
  - compute_absolute: 단일 시점 값 직접 비교(ABSOLUTE/VERIFIABLE).
  - compute_change:   두 시점(현재 evidence.value − 기준 evidence.compare_value)으로
                      절대 증감·증감률을 산출해 비교(CHANGE_RATE).
ratio/distribution 등 다중 claim 그룹연산은 다루지 않는다(Phase 2).
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


# 증감 비교 상대 허용오차. 큰 반올림 증감값(예: "21만6000명 증가"=216000)은 유효숫자
# 절대오차(±0.5)로는 거의 항상 F 라, KOSIS 공식값과의 상대오차 ≤2%(figure-recall 채점과
# 동일 기준)도 함께 허용한다.
_CHANGE_REL_TOL = 0.02
# claim.unit 이 이 집합이면 증감률(%) 비교 — (신−구)/구×100.
_RATE_UNITS = {"%", "퍼센트", "percent", "프로"}


def compute_change(claim: Claim, evidence: Evidence) -> MetricResult:
    """두 시점 증감 비교. CHANGE_RATE claim 전용.

    [5] fetch_kosis_data 가 같은 셀 좌표로 현재(period)·기준(compare_period) 두 시점을
    조회해 evidence.value / evidence.compare_value 에 채워둔다. 여기선
      - claim.unit 이 % 면  증감률 = (신−구)/구 × 100
      - 그 외(명·원·%p 등) 면 절대 증감 = 신−구 (단위 환산)
    를 산출해 claim 수치와 허용오차 비교한다. 두 시점 중 하나라도 없으면 NEI.
    """
    operation = claim.claim_type.value
    parsed = parse_claim_value(claim.value.llm_value)

    if evidence.value is None or evidence.compare_value is None:
        return MetricResult(
            operation=operation,
            claim_value=parsed.number,
            kosis_value=evidence.value,
            verdict=Verdict.NOT_ENOUGH_INFO,
            note="증감 비교 불가(기준 시점 KOSIS 값 없음)",
        )
    if parsed.kind not in (ValueKind.SCALAR, ValueKind.SIGNED) or parsed.number is None:
        return MetricResult(
            operation=operation,
            claim_value=parsed.number,
            kosis_value=evidence.value,
            verdict=Verdict.NOT_ENOUGH_INFO,
            note=f"증감 비교 불가(value kind={parsed.kind.value})",
        )

    v_new, v_old = evidence.value, evidence.compare_value
    claim_num = parsed.number
    unit = (claim.unit or "").strip()
    notes: list[str] = []

    if unit in _RATE_UNITS:
        if v_old == 0:
            return MetricResult(
                operation=operation, claim_value=claim_num, kosis_value=v_new,
                verdict=Verdict.NOT_ENOUGH_INFO, note="증감률 산출 불가(기준값 0)",
            )
        computed = (v_new - v_old) / v_old * 100.0
        notes.append(f"증감률 (신 {v_new} − 구 {v_old})/구 ×100 = {computed:.4g}%")
    else:
        delta = v_new - v_old
        aligned, status = align_value(delta, evidence.unit, claim.unit)
        if status in ("incompatible", "unknown_unit"):
            return MetricResult(
                operation=operation, claim_value=claim_num, kosis_value=delta,
                verdict=Verdict.NOT_ENOUGH_INFO, mismatch_type=MismatchType.UNIT,
                note=f"증감 단위 비교불가({status}): claim={claim.unit!r} kosis={evidence.unit!r}",
            )
        # %p(포인트)는 변화량이라 환산 부적격(non_absolute) → 차이를 그대로 둔다(둘 다 동단위).
        computed = delta if status == "non_absolute" else aligned
        if status == "ok":
            notes.append(f"단위환산 {evidence.unit}→{claim.unit}")
        notes.append(f"절대증감 신 {v_new} − 구 {v_old} = {computed:.4g}")

    tol = tolerance_abs(claim.value.llm_value)
    abs_diff = abs(claim_num - computed)
    rel_base = abs(computed)
    within = abs_diff <= tol or (rel_base > 0 and abs_diff / rel_base <= _CHANGE_REL_TOL)

    mismatch = None
    if not within:
        # 크기는 맞고 부호만 다르면 방향 오류(증가↔감소), 아니면 크기 오류.
        if abs(abs(claim_num) - abs(computed)) <= max(tol, _CHANGE_REL_TOL * rel_base):
            mismatch = MismatchType.DIRECTION
        else:
            mismatch = MismatchType.MAGNITUDE

    if evidence.population_fallback:
        notes.append("population_fallback: 요청 집단 대신 전체값 기준 증감 — [8] 정합성 확인 대상")

    return MetricResult(
        operation=operation,
        claim_value=claim_num,
        kosis_value=v_new,
        computed_value=round(computed, 4),
        rel_diff=abs_diff / rel_base if rel_base > 0 else None,
        within_tolerance=within,
        verdict=Verdict.TRUE if within else Verdict.FALSE,
        mismatch_type=mismatch,
        note="; ".join(notes) or None,
    )
