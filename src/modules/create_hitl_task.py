from __future__ import annotations

from src.schemas.runtime import MasterSchema


class CreateHitlTaskError(Exception):
    """HITL 작업 생성 실패."""


async def create_hitl_task(record: MasterSchema) -> None:
    """
    [HITL] Create HITL Task — 선형 파이프라인 밖(조건부 실행).

    Input:
        record.verifications   # 저신뢰/모호 판정

    Output:
        사람 검토 작업(HITL task)

    Responsibility:
        confidence 가 낮거나 모호한 판정을 사람 검토 큐로 보내는 작업을 생성한다.
        runner 의 선형 _STEPS 에는 포함되지 않으며 조건부로 호출된다.
        실패 시 raise.
    """
    raise NotImplementedError("create_hitl_task 미구현 — HITL 작업 생성 필요")
