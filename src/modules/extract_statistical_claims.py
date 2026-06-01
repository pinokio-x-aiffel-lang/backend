from __future__ import annotations

from src.schemas.runtime import Claim, MasterSchema, ValueSlot


class ExtractStatisticalClaimsError(Exception):
    """클레임 추출 실패 — LLM 응답 파싱 오류 등."""


async def extract_statistical_claims(record: MasterSchema) -> None:
    """
    [2] Extract Statistical Claims

    Input:
        record.article        # [1]에서 적재된 기사

    Output:
        record.claims         # list[Claim] (각 claim_id 부여)

    Responsibility:
        기사 본문에서 수치 기반 사실 주장을 LLM(HCX)으로 추출해
        record.claims 에 채운다.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    # TODO: 실제 구현 — LLM(HCX) 주장 추출. 현재는 happy-path 더미 1건.
    article_id = record.article.article_id if record.article else "art-0001"
    record.claims = [
        Claim(
            claim_id="clm-0001",
            article_id=article_id,
            sentence="(더미) 2024년 합계출산율은 0.72명이다.",
            claim_type="수치",
            subject="합계출산율",
            value=ValueSlot(raw="0.72명", llm_value="", is_inferred=False),
            unit="명",
            aggregation="값",
            period_type="Y",
            period_value=ValueSlot(raw="2024년", llm_value="", is_inferred=False),
            compare_period_value=None,
            population="전국",
            cited_source="통계청",
        )
    ]
