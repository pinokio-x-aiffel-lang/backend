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


# overall_verdict 심각도 우선순위 (높을수록 우선). TODO(full [9])에서 정밀화.
_SEVERITY = {"F": 3, "M": 2, "N": 1, "T": 0}


async def decide_verdict(master_schema: MasterSchema) -> None:
    """
    [9] Decide Verdict (옛 _synthesize + _verdict 통합)

    Input:
        master_schema.verifications.claim_results[*].metric  # [7]~[8] 비교·정합성 결과

    Output:
        master_schema.verifications   # summary(overall_verdict, average_confidence) 확정

    Responsibility:
        [7] 이 생성하고 [8] 이 보정한 claim_results 를 종합해 overall_verdict 를 산출한다.
        현재는 전이 구현 — metric.verdict 를 claim_result.verdict 로 확정하고 요약만
        채운다. confidence(rel_diff→[0,1]) · verdict_human 정밀 산출은 TODO.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    verifications = master_schema.verifications
    if verifications is None:
        # [7] 미실행 등 예외 경로 — claims 로 최소 골격 생성(레거시 폴백).
        verifications = _build_skeleton(master_schema)
        master_schema.verifications = verifications

    for cr in verifications.claim_results:
        metric = cr.metric
        if metric is not None and metric.verdict is not None:
            cr.verdict = metric.verdict.value
            cr.mismatch_type = (
                metric.mismatch_type.value if metric.mismatch_type else cr.mismatch_type
            )
        # TODO(full [9]): confidence(rel_diff→[0,1]) · verdict_human · llm_model.

    verifications.summary = VerificationSummary(
        total_claims=len(verifications.claim_results),
        overall_verdict=_overall_verdict(verifications.claim_results),
        average_confidence=0.0,
    )


def _overall_verdict(claim_results: list[ClaimResult]) -> str:
    """claim별 verdict 중 가장 심각한 것. 비어 있으면 UNVERIFIED."""
    verdicts = [cr.verdict for cr in claim_results if cr.verdict in _SEVERITY]
    if not verdicts:
        return "UNVERIFIED"
    return max(verdicts, key=lambda v: _SEVERITY[v])


def _build_skeleton(master_schema: MasterSchema) -> Verifications:
    """[7] 미실행 시 claims 로 빈 claim_results 골격 생성(레거시 폴백)."""
    evidence_by_claim = {a.claim_id: a.evidence for a in master_schema.analysis}
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
        summary=VerificationSummary(
            total_claims=len(claim_results),
            overall_verdict="UNVERIFIED",
            average_confidence=0.0,
        ),
        claim_results=claim_results,
    )
