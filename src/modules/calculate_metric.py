from __future__ import annotations

from src.schemas.runtime import MasterSchema


class CalculateMetricError(Exception):
    """수치 비교 계산 실패."""


async def calculate_metric(master_schema: MasterSchema) -> None:
    """
    [6] Calculate Metric

    Input:
        master_schema.claims[*].value.llm_value   # 정규화된 주장 수치
        master_schema.analysis (선정 Evidence)     # KOSIS 공식 수치

    Output:
        claim별 초기 verdict / mismatch_type

    Responsibility:
        주장 수치(llm_value)와 KOSIS 증거 수치를 비교해
        일치/불일치와 mismatch_type 초기 판정을 계산한다.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    # TODO: 실제 구현 — 주장 vs 증거 수치 비교. 판정 조립은 [8] decide_verdict.
    print("[6] calculate_metric — KOSIS 값:", [(a.claim_id, a.evidence.value if a.evidence else None) for a in master_schema.analysis])
