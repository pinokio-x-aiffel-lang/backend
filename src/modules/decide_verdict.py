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
    claim_results = [
        ClaimResult(
            claim_id=claim.claim_id,
            verdict="UNVERIFIED",
            claim_value=claim.value.llm_value,
            kosis_value="0.72",
            explanation="",  # [9] generate_explanation 에서 채움
            confidence=0.0,
            llm_model="(더미)",
            evidence=[
                Evidence(
                    claim_id=claim.claim_id,
                    source="KOSIS",
                    subject=claim.subject,
                    unit=claim.unit,
                    period_type=claim.period_type,
                    period=claim.period_value.llm_value,
                    population=claim.population,
                    # value·kosis_*·table_name·url·날짜는 KOSIS 조회([4]~[7]) 전이라 None(기본값)
                )
            ],
        )
        for claim in master_schema.claims
    ]
    master_schema.verifications = Verifications(
        summary=VerificationSummary(
            total_claims=len(claim_results),
            overall_verdict="UNVERIFIED",
            average_confidence=0.0,
        ),
        claim_results=claim_results,
    )
