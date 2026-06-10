from __future__ import annotations

from src.numeric.compare import compute_absolute
from src.numeric.value import ValueKind, parse_claim_value
from src.schemas.runtime import (
    Claim,
    ClaimResult,
    ClaimType,
    Evidence,
    MasterSchema,
    MetricResult,
    Verdict,
    VerificationSummary,
    Verifications,
)


class CalculateMetricError(Exception):
    """수치 비교 계산 실패."""


# 단일 셀 직접비교가 가능한 claim 유형. 나머지(그룹연산)는 상류 미배선(Phase 2).
_ABSOLUTE_TYPES = {ClaimType.ABSOLUTE, ClaimType.VERIFIABLE}
# KOSIS 검증 대상이 아닌 유형.
_SKIP_TYPES = {ClaimType.METAPHORIC, ClaimType.NONE}


async def calculate_metric(master_schema: MasterSchema) -> None:
    """
    [7] Calculate Metric (Numeric Layer)

    Input:
        master_schema.claims[*].value.llm_value   # 정규화된 주장 수치
        master_schema.analysis[*].evidence        # KOSIS 공식 수치(선정 셀)

    Output:
        master_schema.verifications                # 생성(claim_results 스켈레톤)
        master_schema.verifications.claim_results[*].metric: MetricResult

    Responsibility:
        주장 수치(llm_value)와 KOSIS 증거 수치를 비교해 일치(T)/불일치(F) 초기 판정과
        mismatch_type 을 계산하고, claim 별 ClaimResult 를 생성해 metric 에 담는다.
        ABSOLUTE/VERIFIABLE 만 단일 셀 직접비교를 수행하고, 그룹연산은 상류 미배선이라
        모호(M)로 둔다. 모호 케이스 보정은 [8] check_alignment, 최종 판정은 [9].
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    # [5]가 내보낸 매칭 후보 전체(evidences). 없으면 단수 evidence 로 폴백(하위호환).
    evidences_by_claim = {
        a.claim_id: (a.evidences or ([a.evidence] if a.evidence else []))
        for a in master_schema.analysis
    }

    claim_results = [
        _build_claim_result(claim, evidences_by_claim.get(claim.claim_id, []))
        for claim in master_schema.claims
    ]

    master_schema.verifications = Verifications(
        summary=VerificationSummary(
            total_claims=len(claim_results),
            overall_verdict="UNVERIFIED",  # [9] decide_verdict 에서 확정
            average_confidence=0.0,
        ),
        claim_results=claim_results,
    )


def _build_claim_result(claim: Claim, evidences: list[Evidence]) -> ClaimResult:
    metric, chosen = _select_metric(claim, evidences)
    # 채택된 evidence 를 맨 앞으로 — [10] generate_explanation 이 evidence[0]을 출처로
    # 인용하므로, 값(metric)과 출처 표기가 일치하도록 정렬한다.
    ordered = ([chosen] + [e for e in evidences if e is not chosen]) if chosen else list(evidences)
    return ClaimResult(
        claim_id=claim.claim_id,
        # 초기 판정/표시 시드 — [8]·[9]가 보정·확정한다.
        verdict=metric.verdict.value if metric.verdict else "UNVERIFIED",
        mismatch_type=metric.mismatch_type.value if metric.mismatch_type else None,
        claim_value=claim.value.llm_value,
        kosis_value=str(metric.kosis_value) if metric.kosis_value is not None else None,
        metric=metric,
        evidence=ordered,  # 채택 후보가 맨 앞, 그 뒤로 나머지(n)
    )


def _select_metric(
    claim: Claim, evidences: list[Evidence]
) -> tuple[MetricResult, Evidence | None]:
    """후보 n개를 각각 origin 과 비교(n:1)하고 (대표 MetricResult, 채택 evidence)를 고른다.

    우선순위 T > F > NEI, 동급은 상대오차(rel_diff) 작은 것 — 즉 '허용오차 내 일치하는
    후보가 하나라도 있으면 일치(T)로 보고 가장 잘 맞는 표를 채택'한다. skip 유형/무증거는
    바로 NEI(채택 evidence None). 비교(claim_value vs evidence.value)는 _compute_metric 재사용.
    """
    if claim.claim_type in _SKIP_TYPES or not evidences:
        return _compute_metric(claim, None), None  # NEI(검증대상 아님 / 무증거)
    pairs = [(_compute_metric(claim, ev), ev) for ev in evidences]
    metric, chosen = min(pairs, key=lambda p: _metric_rank(p[0]))
    return metric, chosen


def _metric_rank(m: MetricResult) -> tuple[int, float]:
    order = {Verdict.TRUE: 0, Verdict.FALSE: 1}.get(m.verdict, 2)  # T < F < NEI
    rd = m.rel_diff if m.rel_diff is not None else float("inf")
    return (order, rd)


def _compute_metric(claim: Claim, evidence: Evidence | None) -> MetricResult:
    operation = claim.claim_type.value

    if claim.claim_type in _SKIP_TYPES:
        return MetricResult(
            operation=operation,
            verdict=Verdict.NOT_ENOUGH_INFO,
            note="KOSIS 검증 대상 아님(metaphoric/none)",
        )

    if evidence is None or evidence.value is None:
        return MetricResult(
            operation=operation,
            claim_value=_scalar_or_none(claim),
            verdict=Verdict.NOT_ENOUGH_INFO,
            note="KOSIS 매칭 없음",
        )

    if claim.claim_type in _ABSOLUTE_TYPES:
        return compute_absolute(claim, evidence)

    # 그룹연산 — compare_conquer(그룹핑)·다중셀 조회가 없어 현재 산출 불가(Phase 2) → NEI.
    return MetricResult(
        operation=operation,
        kosis_value=evidence.value,
        verdict=Verdict.NOT_ENOUGH_INFO,
        note="그룹연산 미배선(claim 그룹핑·다중셀 조회 선행 필요)",
    )


def _scalar_or_none(claim: Claim) -> float | None:
    parsed = parse_claim_value(claim.value.llm_value)
    return parsed.number if parsed.kind in (ValueKind.SCALAR, ValueKind.SIGNED) else None
