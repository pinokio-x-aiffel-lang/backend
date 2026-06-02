from __future__ import annotations

from src.schemas.runtime import MasterSchema


class NormalizeClaimError(Exception):
    """클레임 정규화 실패 — 한국어 수치/시점 파싱 오류 등."""


async def normalize_claim(master_schema: MasterSchema) -> None:
    """
    [3] Normalize Claim

    Input:
        master_schema.claims

    Output:
        master_schema.claims[*].value.llm_value
        master_schema.claims[*].period_value.llm_value

    Responsibility:
        "약 23만" → "230000", "전년" → "2023" 등 한국어 수사·시점을
        산술값으로 정규화해 각 claim 슬롯의 llm_value 를 제자리 갱신한다.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    # TODO: 실제 구현 — 한국어 수치/시점 정규화. 현재는 happy-path 더미.
    for claim in master_schema.claims:
        claim.value.llm_value = "0.72"
        claim.period_value.llm_value = "2024"
