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


async def decide_verdict(master_schema: MasterSchema) -> None:
    """
    [8] Decide Verdict (옛 _synthesize + _verdict 통합)

    Input:
        master_schema.claims + 비교·정합성 결과([6]~[7])

    Output:
        master_schema.verifications   # summary(overall_verdict, average_confidence) + claim_results

    Responsibility:
        claim별 판정을 종합해 overall_verdict / average_confidence 를 산출하고,
        결과를 Verifications 스키마로 조립해 master_schema.verifications 에 채운다.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    # TODO: 실제 구현 — [6]~[7] 결과로 판정. 현재는 happy-path 더미(UNVERIFIED).
    # claim_id → KOSIS 조회 근거(Evidence). 미조회/실패 시 None.
    evidence_by_claim = {a.claim_id: a.evidence for a in master_schema.analysis}

    claim_results = []
    for claim in master_schema.claims:
        evidence = evidence_by_claim.get(claim.claim_id)
        # KOSIS 공식 수치 — 조회된 evidence 가 있을 때만. 없으면 None(더미값 금지).
        kosis_value = (
            str(evidence.value)
            if evidence is not None and evidence.value is not None
            else None
        )
        claim_results.append(
            ClaimResult(
                claim_id=claim.claim_id,
                verdict="UNVERIFIED",
                claim_value=claim.value.llm_value,
                kosis_value=kosis_value,
                explanation="",  # [9] generate_explanation 에서 채움
                confidence=0.0,
                llm_model="(더미)",
                evidence=[evidence] if evidence is not None else [
                    Evidence(
                        claim_id=claim.claim_id,
                        source="KOSIS",
                        subject=claim.subject,
                        unit=claim.unit,
                        period_type=claim.period_type,
                        period=claim.period_value.llm_value,
                        population=claim.population,
                        # KOSIS 조회 실패 — value·kosis_*·table_name·url·날짜는 None(기본값)
                    )
                ],
            )
        )
    master_schema.verifications = Verifications(
        summary=VerificationSummary(
            total_claims=len(claim_results),
            overall_verdict="UNVERIFIED",
            average_confidence=0.0,
        ),
        claim_results=claim_results,
    )
