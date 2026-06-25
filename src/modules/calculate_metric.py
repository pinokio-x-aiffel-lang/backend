from __future__ import annotations

from src.numeric.compare import _is_delta_evidence, compute_absolute, compute_change
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

    # 모집단 폴백(전부 전체값 대체)도 NEI 로 막지 않고 전체값과 수치비교해 T/F 를 낸다.
    # 7단계는 '값' 만 보고, 요청 집단↔전체 오도(모집단 M)는 [8] check_alignment 가
    # 원문 맥락으로 판정한다 — 폴백을 7단계에서 NEI 로 죽이면 그 M 판정 기회가 사라진다.
    # (compute_absolute 가 evidence.population_fallback 를 note 로 남겨 [8] 대상임을 표시.)

    # CHANGE_RATE 는 증감표(value=델타)가 절대표보다 정답 소스 → 앞으로 당김(안정 정렬).
    if claim.claim_type == ClaimType.CHANGE_RATE:
        evidences = sorted(evidences, key=lambda e: 0 if _is_delta_evidence(e) else 1)

    top = evidences[0]                       # [6]이 고른 1위 적합 표
    top_metric = _compute_metric(claim, top)
    if top_metric.verdict == Verdict.TRUE:   # 1위 표와 일치 → 확정(→[8] 정합성)
        return top_metric, False, None

    # 1위 불일치 → [값앵커 역매칭] 나머지 표를 전부 비교한다.
    #   값 일치 + 라벨검증(그 셀의 집단이 claim 집단에 실제 매칭 = population_fallback 아님)인
    #   표가 있으면 채택해 T(NEI 누수 방지). 라벨검증이 우연 값충돌(false-T)을 막는 핵심:
    #   값만 같고 집단이 안 맞으면(폴백=전체값 대체) 승격하지 않는다.
    fallback_T = False
    for ev in evidences[1:]:
        m = _compute_metric(claim, ev)
        if m.verdict != Verdict.TRUE:
            continue
        if not getattr(ev, "population_fallback", False):
            note = (m.note + " | " if m.note else "") \
                + "1위 불일치 → 값·집단라벨 일치하는 타 표 채택(값앵커 역매칭)"
            return m.model_copy(update={"note": note}), False, None
        fallback_T = True

    if fallback_T:
        # 값은 맞지만 집단 라벨 미검증(전체값 폴백) → 우연 충돌 위험 → NEI + HITL(라벨러 판단).
        m = top_metric.model_copy(update={
            "verdict": Verdict.NOT_ENOUGH_INFO,
            "mismatch_type": None,
            "note": (top_metric.note + " | " if top_metric.note else "")
            + "1위 불일치·타 표는 값만 맞고 집단 라벨 미검증(폴백) → 라벨러 검토",
        })
        return m, True, "타 표 값일치하나 집단 라벨 미검증(폴백) → 사람 판단 필요"

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
