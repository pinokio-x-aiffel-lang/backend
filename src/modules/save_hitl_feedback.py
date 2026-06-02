from __future__ import annotations

from src.schemas.runtime import MasterSchema


class SaveHitlFeedbackError(Exception):
    """HITL 피드백 저장 실패."""


async def save_hitl_feedback(master_schema: MasterSchema) -> None:
    """
    [HITL] Save HITL Feedback — 선형 파이프라인 밖(검토 후 별도 진입점).

    Input:
        master_schema + 사람 검토 결과 (입력 계약 TBD)

    Output:
        반영된 판정(verdict_human / verdict_human_note 등) 저장

    Responsibility:
        사람 검토 결과를 판정에 반영해 저장한다.
        파이프라인 실행과 분리된 콜백 진입점으로, runner 가 호출하지 않는다.
        실패 시 raise.
    """
    raise NotImplementedError("save_hitl_feedback 미구현 — 사람 검토 결과 반영 필요")
