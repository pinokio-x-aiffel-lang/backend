from __future__ import annotations

from src.schemas.runtime import MasterSchema


class GenerateExplanationError(Exception):
    """설명 생성 실패."""


async def generate_explanation(master_schema: MasterSchema) -> None:
    """
    [9] Generate Explanation

    Input:
        master_schema.verifications   # [8]에서 조립된 판정 결과

    Output:
        master_schema.verifications.claim_results[*].explanation

    Responsibility:
        verdict 와 수치 차이를 근거로 한국어 자연어 설명을 LLM 으로 생성해
        각 claim_result 의 explanation 을 채운다.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    # TODO: 실제 구현 — LLM 설명 생성. 현재는 happy-path 더미.
    if master_schema.verifications is None:
        return
    for result in master_schema.verifications.claim_results:
        result.explanation = "(더미) 검증 설명 — 실제 구현 전 placeholder"
