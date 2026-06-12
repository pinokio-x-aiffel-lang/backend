from __future__ import annotations

from src.schemas.runtime import (
    ClaimResult,
    Evidence,
    MasterSchema,
    VerificationSummary,
    Verifications,
)


class DecideVerdictError(Exception):
    """검증 결과 판정/조립 실패."""


_VERDICT_CODES = ("T", "F", "M", "N")


async def decide_verdict(master_schema: MasterSchema) -> None:
    """
    [9] Decide Verdict

    Input:
        master_schema.verifications.claim_results[*].metric  # [7]~[8] 비교·정합성 결과

    Output:
        master_schema.verifications.claim_results[*].verdict / mismatch_type  # metric 으로 확정
        master_schema.verifications.summary  # verdict_counts·overall_confidence·coverage 확정

    Responsibility:
        [7]이 생성하고 [8]이 보정한 claim_results 를 종합한다.
          1) claim별: metric.verdict 를 claim_result.verdict 로 확정한다.
          2) 기사별: verdict 분포(verdict_counts)와 두 지표를 산출한다.
             - overall_confidence = T / (T+F+M)    (검증된 것 중 사실 비율, N 제외)
             - coverage           = (T+F+M) / total (검증해낸 비율; N=미검증)
        단일 종합 라벨은 더 내지 않는다 — 분포(verdict_counts)를 프론트가 받아 표시한다.
        N 의 세부 사유(데이터 모호/시스템 장애)는 상류가 찍은 needs_hitl·hitl_category 를
        그대로 보존한다([9]는 가공하지 않음).
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    verifications = master_schema.verifications
    if verifications is None:
        # [7] 미실행 등 예외 경로 — claims 로 최소 골격 생성(레거시 폴백).
        verifications = _build_skeleton(master_schema)
        master_schema.verifications = verifications

    # 1) claim별 verdict 확정 ([8] 까지 보정된 metric.verdict 를 표시 필드로).
    for cr in verifications.claim_results:
        metric = cr.metric
        if metric is not None and metric.verdict is not None:
            cr.verdict = metric.verdict.value
            cr.mismatch_type = (
                metric.mismatch_type.value if metric.mismatch_type else cr.mismatch_type
            )

    # 2) 기사 단위 분포·지표 산출.
    counts = _count_verdicts(verifications.claim_results)
    total = len(verifications.claim_results)
    resolved = counts["T"] + counts["F"] + counts["M"]  # 판정이 선 건(N 제외)

    summary = verifications.summary
    summary.total_claims = total
    summary.verdict_counts = counts
    summary.overall_confidence = counts["T"] / resolved if resolved else 0.0
    summary.coverage = resolved / total if total else 0.0


def _count_verdicts(claim_results: list[ClaimResult]) -> dict[str, int]:
    """claim별 verdict 분포. T/F/M/N 외 값(UNVERIFIED 등)은 N(검증 불가)으로 집계."""
    counts = {code: 0 for code in _VERDICT_CODES}
    for cr in claim_results:
        counts[cr.verdict if cr.verdict in counts else "N"] += 1
    return counts


def _build_skeleton(master_schema: MasterSchema) -> Verifications:
    """[7] 미실행 시 claims 로 빈 claim_results 골격 생성(레거시 폴백).

    summary 의 분포·지표는 본 산출이 덮어쓰므로 여기선 기본값만 둔다.
    """
    evidence_by_claim = {
        a.claim_id: (a.evidences[0] if a.evidences else None)
        for a in master_schema.analysis
    }
    claim_results = []
    for claim in master_schema.claims:
        evidence = evidence_by_claim.get(claim.claim_id)
        kosis_value = (
            str(evidence.value)
            if evidence is not None and evidence.value is not None
            else None
        )
        claim_results.append(
            ClaimResult(
                claim_id=claim.claim_id,
                claim_value=claim.value.llm_value,
                kosis_value=kosis_value,
                evidence=[evidence] if evidence is not None else [
                    Evidence(
                        claim_id=claim.claim_id,
                        source="KOSIS",
                        subject=claim.subject,
                        unit=claim.unit,
                        period_type=claim.period_type,
                        period=claim.period_value.llm_value,
                        population=claim.population,
                    )
                ],
            )
        )
    return Verifications(
        summary=VerificationSummary(total_claims=len(claim_results)),
        claim_results=claim_results,
    )
