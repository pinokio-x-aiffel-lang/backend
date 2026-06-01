from __future__ import annotations

from src.schemas.runtime import MasterSchema


class CalculateMetricError(Exception):
    """수치 비교 계산 실패."""


async def calculate_metric(record: MasterSchema) -> None:
    """
    [7] Calculate Metric

    Input:
        record.claims[*].value.llm_value   # 정규화된 주장 수치
        record.analysis (선정 Evidence)     # KOSIS 공식 수치

    Output:
        claim별 초기 verdict / mismatch_type

    Responsibility:
        주장 수치(llm_value)와 KOSIS 증거 수치를 비교해
        일치/불일치와 mismatch_type 초기 판정을 계산한다.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    # TODO: 실제 구현 — 주장 vs 증거 수치 비교.
    #       판정 조립은 [9] decide_verdict 에서. happy-path 에선 no-op.
    pass
