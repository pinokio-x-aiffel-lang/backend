from __future__ import annotations

from src.schemas.runtime import MasterSchema


class CheckAlignmentError(Exception):
    """정합성 판단 실패."""


async def check_alignment(master_schema: MasterSchema) -> None:
    """
    [7] Check Alignment

    Input:
        master_schema.claims + 비교 결과([6])

    Output:
        모호 케이스 재판정 결과

    Responsibility:
        수치 비교만으로 판단이 어려운 케이스(단위 불일치·집계 방식 차이 등)를
        LLM 으로 재판정해 주장-통계 정합성을 보정한다.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    # TODO: 실제 구현 — 모호 케이스 LLM 재판정. happy-path 에선 no-op.
    pass
