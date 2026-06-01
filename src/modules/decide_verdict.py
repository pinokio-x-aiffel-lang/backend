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


async def decide_verdict(record: MasterSchema) -> None:
    """
    [9] Decide Verdict (옛 _synthesize + _verdict 통합)

    Input:
        record.claims + 비교·정합성 결과([7]~[8])

    Output:
        record.verifications   # summary(overall_verdict, average_confidence) + claim_results

    Responsibility:
        claim별 판정을 종합해 overall_verdict / average_confidence 를 산출하고,
        결과를 Verifications 스키마로 조립해 record.verifications 에 채운다.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    # TODO: 실제 구현 — [7]~[8] 결과로 판정. 현재는 happy-path 더미(UNVERIFIED).
    claim_results = [
        ClaimResult(
            claim_id=claim.claim_id,
            verdict="UNVERIFIED",
            claim_value=claim.value.llm_value,
            kosis_value="0.72",
            explanation="",  # [10] generate_explanation 에서 채움
            confidence=0.0,
            llm_model="(더미)",
            evidence=[
                Evidence(
                    evidence_id="ev-0001",
                    claim_id=claim.claim_id,
                    source="KOSIS",
                    subject=claim.subject,
                    value=0.72,
                    unit=claim.unit,
                    period_type=claim.period_type,
                    period=claim.period_value.llm_value,
                    population=claim.population,
                    kosis_org_id="101",
                    kosis_tbl_id="DT_DUMMY",
                    table_name="(더미) 인구동향조사",
                    kosis_item_id="T1",
                    url="https://kosis.kr",
                    last_updated="2024-01-01",
                    retrieved_at="2024-01-01",
                )
            ],
        )
        for claim in record.claims
    ]
    record.verifications = Verifications(
        summary=VerificationSummary(
            total_claims=len(claim_results),
            overall_verdict="UNVERIFIED",
            average_confidence=0.0,
        ),
        claim_results=claim_results,
    )
