"""소형 슬롯 스키마 Pydantic 모델.

기준 문서: ../../../4_아키텍쳐 설계/슬롯 스키마/슬롯 스키마.md
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


PeriodType = Literal["Y", "M", "Q", "D"]


class ValueSlot(BaseModel):
    """수치 또는 시점 슬롯. value / period_value / compare_period_value 공통 구조."""

    raw: str = Field(alias="Original_table")
    llm_value: str = Field(alias="LLM_Metrics")
    is_inferred: bool = Field(alias="Inferred")

    model_config = ConfigDict(populate_by_name=True)


class Claim(BaseModel):
    """기사 한 문장에서 추출된 수치 기반 사실 주장."""

    claim_id: str
    article_id: str
    sentence: str
    claim_type: str
    subject: str
    value: ValueSlot
    unit: str
    aggregation: str
    period_type: PeriodType
    period_value: ValueSlot
    compare_period_value: ValueSlot | None = None
    population: str
    cited_source: str

    model_config = ConfigDict(populate_by_name=True)


class Claims(BaseModel):
    """LLM 응답 파싱용 래퍼 — `{ "claims": [...] }` 구조 그대로 매칭."""

    claims: list[Claim]

    model_config = ConfigDict(populate_by_name=True)
