from __future__ import annotations

from src.numeric.compare import compute_absolute, compute_change
from src.numeric.value import ValueKind, parse_claim_value
from src.schemas.runtime import (
    Claim,
    ClaimResult,
    ClaimType,
    Evidence,
    HitlCategory,
    MasterSchema,
    MetricResult,
    Verdict,
    VerificationSummary,
    Verifications,
)


class CalculateMetricError(Exception):
    """수치 비교 계산 실패."""


# 단일 셀 직접비교가 가능한 claim 유형. 나머지(다중 claim 그룹연산)는 상류 미배선(Phase 2).
_ABSOLUTE_TYPES = {ClaimType.ABSOLUTE, ClaimType.VERIFIABLE}
# 단일 표 1:1 비교가 가능한 유형(표 선정 로직 공유) — 절대형 + 증감형(2시점 차).
# CHANGE_RATE 는 같은 셀의 현재·기준 두 시점을 [5]가 조회해 evidence 에 담아둔다.
_COMPARABLE_TYPES = _ABSOLUTE_TYPES | {ClaimType.CHANGE_RATE}
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
    # [5]가 내보낸 매칭 후보 전체(evidences). [6]이 1위를 evidences[0]으로 정렬해 둔다.
    evidences_by_claim = {a.claim_id: a.evidences for a in master_schema.analysis}

    claim_results = [
        _build_claim_result(claim, evidences_by_claim.get(claim.claim_id, []))
        for claim in master_schema.claims
    ]

    master_schema.verifications = Verifications(
        summary=VerificationSummary(
            total_claims=len(claim_results),
            # 분포·신뢰도·검증률은 [9] decide_verdict 에서 확정 (여기선 기본값).
        ),
        claim_results=claim_results,
    )


def _build_claim_result(claim: Claim, evidences: list[Evidence]) -> ClaimResult:
    """[6]이 정렬한 evidences[0](=1위 적합 표) 기준으로 판정한다.

    1위 표 비교가 T → T(다음 [8]로). T 아니면(F) 나머지 표에 근사값(T 가능)이 있으면
    NEI + needs_hitl(라벨러 판단), 없으면 F. 무증거/비절대형/요청 집단 전부 폴백은 NEI.
    evidences[0] 을 항상 대표 출처로 둬 값·출처 표기를 일치시킨다([10] evidence[0] 인용).
    """
    metric, needs_hitl, hitl_reason = _decide_metric(claim, evidences)
    return ClaimResult(
        claim_id=claim.claim_id,
        # 초기 판정/표시 시드 — [8]·[9]가 보정·확정한다(verdict 은 metric.verdict 로 전파).
        verdict=metric.verdict.value if metric.verdict else "UNVERIFIED",
        mismatch_type=metric.mismatch_type.value if metric.mismatch_type else None,
        claim_value=claim.value.llm_value,
        kosis_value=str(metric.kosis_value) if metric.kosis_value is not None else None,
        metric=metric,
        evidence=list(evidences),  # [6] 정렬: [0]=1위 표
        needs_hitl=needs_hitl,
        # 7단계의 유일한 HITL 트리거는 데이터 모호(1위 불일치+타 표 근사값).
        hitl_category=HitlCategory.DATA_AMBIGUITY if needs_hitl else None,
        hitl_reason=hitl_reason,
    )


def _decide_metric(
    claim: Claim, evidences: list[Evidence]
) -> tuple[MetricResult, bool, str | None]:
    """(대표 metric, needs_hitl, hitl_reason). 표 선정은 [6]이 끝냄 — 여기선 1위부터 비교."""
    # 그룹연산(ratio 등)·검증대상 아님·무증거 → NEI (표 선정과 무관).
    if claim.claim_type in _SKIP_TYPES or not evidences:
        return _compute_metric(claim, None), False, None
    if claim.claim_type not in _COMPARABLE_TYPES:
        return _compute_metric(claim, evidences[0]), False, None  # 그룹연산 → NEI

    # 요청 집단을 어느 표에서도 못 맞춰 전부 전체값 폴백뿐이면 → 검증 불가(NEI).
    # (예: '북한'처럼 표 모집단 축에 없는 집단 — 전국 합계로 대체된 값만 남은 상태.
    #  전체값과 비교해 우연히 T/F 가 나오는 오염을 막는다.)
    if all(ev.population_fallback for ev in evidences):
        base = _compute_metric(claim, evidences[0])
        m = base.model_copy(update={
            "verdict": Verdict.NOT_ENOUGH_INFO,
            "mismatch_type": None,
            "note": (base.note + " | " if base.note else "")
            + "요청 집단을 어느 표에서도 매칭 못 함(전부 전체값 폴백) → 검증 불가",
        })
        return m, False, None

    top = evidences[0]                       # [6]이 고른 1위 적합 표
    top_metric = _compute_metric(claim, top)
    if top_metric.verdict == Verdict.TRUE:   # 1위 표와 일치 → 확정(→[8] 정합성)
        return top_metric, False, None

    # 1위 표 불일치 → 나머지 표에 근사값(허용오차 내 = T 가능)이 있나?
    has_other_T = any(
        _compute_metric(claim, ev).verdict == Verdict.TRUE for ev in evidences[1:]
    )
    if has_other_T:
        # 적합 표는 불일치인데 다른 표는 맞음 → 애매 → NEI + HITL(라벨러 판단).
        m = top_metric.model_copy(update={
            "verdict": Verdict.NOT_ENOUGH_INFO,
            "mismatch_type": None,
            "note": (top_metric.note + " | " if top_metric.note else "")
            + "1위 적합 표와는 불일치하나 타 표에 근사값 존재 → 라벨러 검토",
        })
        return m, True, "1위 적합 표와 불일치하나 다른 표에 근사값이 있어 사람 판단 필요"

    # 어느 표에도 근사값 없음 → 1위 표 기준 거짓(F).
    return top_metric, False, None


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

    if claim.claim_type == ClaimType.CHANGE_RATE:
        return compute_change(claim, evidence)  # 2시점 차(현재−기준)

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
