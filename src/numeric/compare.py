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


def _granularity_exp(s: str) -> int:
    """표기 마지막 유효자리의 10의 지수(=반올림한 자리).

    소수는 음수(유효 소수자릿수), 정수는 끝의 0 개수만큼 양수.
    '0.75'→-2, '5'→0, '3.0'→0, '238317'→0, '238300'→+2, '238000'→+3, '230000'→+4.
    """
    s = (s or "").strip().lstrip("+-").replace(",", "")
    if "." in s:
        return -len(s.split(".", 1)[1].rstrip("0"))   # 소수 유효자릿수
    digits = s.rstrip("0")
    return len(s) - len(digits) if digits else 0       # 정수 끝 0 개수


def tolerance_abs(claim_repr: str) -> float:
    """유효숫자(반올림) 허용오차 = 마지막 표기 자리의 ±0.5 (자릿수마다 자동).

    소수: '3.5'→±0.05, '0.75'→±0.005, '3.0'→±0.5.
    정수 끝0(반올림): '5'→±0.5, '238300'→±50, '238000'→±500, '230000'→±5000.
    """
    return 0.5 * (10 ** _granularity_exp(claim_repr))


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


def _parse_range(raw: str) -> tuple[float | None, float | None] | None:
    """범위/부등 표기 → (lo, hi) 경계. 수치 경계가 없으면(>=절반·전국평균) None → NEI 유지.

    '50~100'→(50,100), '>=89'→(89,None), '>130'→(130,None), '<75'→(None,75), '<=50'→(None,50).
    초과/이상(>,>=)·미만/이하(<,<=)는 경계 포함으로 근사한다(반올림 노이즈 < 부등호 엄밀성).
    """
    s = (raw or "").strip().replace(",", "")
    nums = re.findall(r"\d[\d.]*", s)
    if "~" in s and len(nums) >= 2:
        a, b = float(nums[0]), float(nums[1])
        return (min(a, b), max(a, b))
    if not nums:
        return None
    x = float(nums[0])
    if s[:1] == ">":
        return (x, None)
    if s[:1] == "<":
        return (None, x)
    return None


# 단위 메타로 환산이 안 될 때 '스케일 근사 가정비교'를 허용하는 배율 상한.
# 두 값의 배율이 이 안이면 같은 척도로 보고 비교한다(claim 단위 '불명'·미인식 구제).
# 세 33.9 ↔ 건 178734(배율 ~5000)처럼 크게 벌어지면 셀 오매칭 신호 → 가정 거부(NEI 유지).
_ASSUME_SCALE_FACTOR = 100.0


def _scale_compatible(a: float, b: float, factor: float = _ASSUME_SCALE_FACTOR) -> bool:
    """두 값이 같은 척도로 볼 만큼 가까운가(절대값 배율 ≤ factor). 0 은 양쪽 0일 때만 호환."""
    a, b = abs(a), abs(b)
    if a == 0 or b == 0:
        return a == b
    return max(a, b) / min(a, b) <= factor


def compute_absolute(claim: Claim, evidence: Evidence) -> MetricResult:
    """단일 셀 직접비교. evidence.value 가 있는 ABSOLUTE/VERIFIABLE claim 전용.

    호출 전제: evidence is not None and evidence.value is not None.
    """
    operation = claim.claim_type.value
    parsed = parse_claim_value(claim.value.llm_value)
    kosis_raw = evidence.value

    # 범위/부등(50~100·>=89)은 수치 경계가 있으면 '포함 비교'로 살린다(단일값 아니라 범위).
    rng = _parse_range(parsed.raw) if parsed.kind == ValueKind.RANGE else None
    # 비스칼라이고 범위경계도 못 뽑으면(비/방향만/파싱불가/'절반'류) 단일 절대비교 불가 → NEI
    if parsed.kind != ValueKind.SCALAR and rng is None:
        return MetricResult(
            operation=operation,
            claim_value=parsed.number,
            kosis_value=kosis_raw,
            verdict=Verdict.NOT_ENOUGH_INFO,
            note=f"단일 절대비교 불가(value kind={parsed.kind.value})",
        )

    aligned, status = align_value(kosis_raw, evidence.unit, claim.unit)
    # KOSIS 단위 메타가 비어있으면(누락) 단위 비교를 포기하지 말고 claim 단위로 가정해 값 비교한다.
    # 빈 단위는 '미지의 단위'가 아니라 '메타 누락' — 값이 정확해도 NEI 로 죽던 문제(M→T→[8] 차단)를 푼다.
    if status == "unknown_unit" and not (evidence.unit or "").strip():
        aligned, status = kosis_raw, "assumed_same"
    # [방법1/3] claim 단위 '불명'·미인식 단위 — 환산은 불가하나 두 값 스케일이 근사하면
    # 같은 척도로 보고 '가정비교'한다. 이 가정은 근사라 불일치 시 confident F 를 내지 않는다
    # (아래 회귀 완화). 스케일이 크게 벌어지면 셀 오매칭 신호 → 가정 거부(NEI 유지).
    unit_assumed = False
    if (
        status in ("unknown_unit", "incompatible")
        and rng is None
        and parsed.kind == ValueKind.SCALAR
        and _scale_compatible(parsed.number, kosis_raw)
    ):
        aligned, status, unit_assumed = kosis_raw, "assumed_scale", True
    if status in ("incompatible", "unknown_unit", "non_absolute"):
        return MetricResult(
            operation=operation,
            claim_value=parsed.number,
            kosis_value=kosis_raw,
            verdict=Verdict.NOT_ENOUGH_INFO,
            mismatch_type=MismatchType.UNIT,
            note=f"단위 비교불가({status}): claim={claim.unit!r} kosis={evidence.unit!r}",
        )

    notes: list[str] = []
    if status == "ok":
        notes.append(f"단위환산 {evidence.unit}→{claim.unit}")
    elif status == "assumed_same":
        notes.append("KOSIS 단위 메타 누락 → claim 단위로 가정 비교")
    elif status == "assumed_scale":
        notes.append(f"단위 미해소(claim={claim.unit!r} kosis={evidence.unit!r}) → 스케일 근사 가정비교")

    # 범위 포함 비교 — 경계 [lo,hi] 안에 KOSIS 값이 들어오면 T, 아니면 F(MAGNITUDE).
    if rng is not None:
        lo, hi = rng
        within = (lo is None or aligned >= lo) and (hi is None or aligned <= hi)
        bound = f"{'-∞' if lo is None else lo}~{'∞' if hi is None else hi}"
        notes.append(f"범위 포함비교 [{bound}] ∋ {aligned}? {'예' if within else '아니오'}")
        if evidence.population_fallback:
            notes.append("population_fallback: 요청 집단 대신 전체(합계)값과 비교 — [8] 정합성 확인 대상")
        return MetricResult(
            operation=operation,
            claim_value=None,
            kosis_value=aligned,
            within_tolerance=within,
            verdict=Verdict.TRUE if within else Verdict.FALSE,
            mismatch_type=None if within else MismatchType.MAGNITUDE,
            note="; ".join(notes) or None,
        )

    claim_value = parsed.number
    abs_diff = abs(claim_value - aligned)
    rel_diff = abs_diff / abs(aligned) if aligned != 0 else None
    if aligned == 0:
        notes.append("기준값 0 — rel_diff 산출 불가")

    tol = tolerance_abs(claim.value.llm_value)
    within = abs_diff <= tol

    # [회귀 완화] 단위를 '가정'해 비교한 경우(assumed_scale) 불일치는 단위·셀 오매칭일 수
    # 있으므로 confident F 를 내지 않고 NEI(검토필요)로 둔다 — 맞는 기사를 거짓이라 단정하는
    # false-F 방지. 일치(within)면 T 유지(→[8] 정합성 재검토가 단위 오도를 거른다).
    if unit_assumed and not within:
        return MetricResult(
            operation=operation,
            claim_value=claim_value,
            kosis_value=aligned,
            rel_diff=rel_diff,
            within_tolerance=False,
            verdict=Verdict.NOT_ENOUGH_INFO,
            mismatch_type=MismatchType.UNIT,
            note="; ".join([*notes, "단위 가정 비교 불일치 → 검토 필요(억지 F 방지)"]) or None,
        )

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


_DELTA_MARKERS = ("증감", "증가수", "증감률", "증감액", "감소수")


def _is_delta_evidence(evidence: Evidence) -> bool:
    """표/주제 이름이 '증감' 류면 evidence.value 가 이미 델타(변화량)다.

    이 경우 compute_change 는 기준시점(compare_value) 없이 value 를 델타로 직접 비교한다
    (증감표는 현재−기준이 아니라 변화량 자체를 한 셀에 담음). 휴리스틱이라 불일치는 NEI.
    """
    text = f"{getattr(evidence, 'table_name', '') or ''} {getattr(evidence, 'subject', '') or ''}"
    return any(m in text for m in _DELTA_MARKERS)


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
    is_delta_tbl = _is_delta_evidence(evidence)  # 증감표: value 가 이미 델타(기준시점 불요)

    if evidence.value is None or (evidence.compare_value is None and not is_delta_tbl):
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
    unit_assumed = False

    if unit in _RATE_UNITS:
        if is_delta_tbl:
            computed = v_new  # 증감(률)표: value 가 이미 변화량/률
            unit_assumed = True  # 휴리스틱 → 불일치 시 confident F 보류(NEI)
            notes.append(f"증감표 직접비교(델타={v_new})")
        elif v_old == 0:
            return MetricResult(
                operation=operation, claim_value=claim_num, kosis_value=v_new,
                verdict=Verdict.NOT_ENOUGH_INFO, note="증감률 산출 불가(기준값 0)",
            )
        else:
            computed = (v_new - v_old) / v_old * 100.0
            notes.append(f"증감률 (신 {v_new} − 구 {v_old})/구 ×100 = {computed:.4g}%")
    else:
        delta = v_new if is_delta_tbl else (v_new - v_old)
        if is_delta_tbl:
            unit_assumed = True  # 증감표 직접비교(휴리스틱) → 불일치 시 NEI(억지 F 방지)
        aligned, status = align_value(delta, evidence.unit, claim.unit)
        # [방법2] KOSIS 단위 빈(메타 누락) → claim 단위로 가정. 증감은 두 셀(현재·기준)이
        # 얽혀 셀 오매칭 위험이 커, 빈단위도 '가정'으로 보고 불일치 시 F 를 보류한다
        # (예: 30~34세 출산율 +3.7 을 합계출산율 셀 0.748 에 매칭 → 억지 F 방지).
        if status == "unknown_unit" and not (evidence.unit or "").strip():
            aligned, status, unit_assumed = delta, "assumed_same", True
        # [방법1/3] claim 단위 '불명'·미인식 — 스케일 근사면 delta 그대로 가정비교(불일치 시 F 보류).
        if status in ("unknown_unit", "incompatible") and _scale_compatible(claim_num, delta):
            aligned, status, unit_assumed = delta, "assumed_scale", True
        if status in ("incompatible", "unknown_unit"):
            return MetricResult(
                operation=operation, claim_value=claim_num, kosis_value=delta,
                verdict=Verdict.NOT_ENOUGH_INFO, mismatch_type=MismatchType.UNIT,
                note=f"증감 단위 비교불가({status}): claim={claim.unit!r} kosis={evidence.unit!r}",
            )
        # %p(포인트)는 변화량이라 환산 부적격(non_absolute) → 차이를 그대로 둔다(둘 다 동단위).
        computed = delta if status in ("non_absolute", "assumed_same", "assumed_scale") else aligned
        if status == "ok":
            notes.append(f"단위환산 {evidence.unit}→{claim.unit}")
        elif status == "assumed_same":
            notes.append("KOSIS 단위 메타 누락 → claim 단위로 가정 비교")
        elif status == "assumed_scale":
            notes.append(f"단위 미해소(claim={claim.unit!r} kosis={evidence.unit!r}) → 스케일 근사 가정비교")
        notes.append(
            f"증감표 델타={computed:.4g}" if is_delta_tbl
            else f"절대증감 신 {v_new} − 구 {v_old} = {computed:.4g}"
        )

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

    # [회귀 완화] 단위를 '가정'해 증감 비교한 경우, 불일치는 단위·셀 오매칭일 수 있어
    # confident F 대신 NEI(검토필요)로 둔다(억지 F 방지). 일치면 T 유지(→[8] 재검토).
    if unit_assumed and not within:
        return MetricResult(
            operation=operation, claim_value=claim_num, kosis_value=v_new,
            computed_value=round(computed, 4), within_tolerance=False,
            verdict=Verdict.NOT_ENOUGH_INFO, mismatch_type=MismatchType.UNIT,
            note="; ".join([*notes, "단위 가정 증감 비교 불일치 → 검토 필요(억지 F 방지)"]) or None,
        )

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
