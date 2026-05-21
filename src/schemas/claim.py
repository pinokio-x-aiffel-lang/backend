"""슬롯 스키마 마스터 Pydantic 모델.

기준 문서: src/schemas/slot_schema_master_v2.json
파이프라인 1건의 전체 산출물(article → claims → analysis → verifications)을 표현한다.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PeriodType = Literal["Y", "M", "Q", "D"]


# --------------------------------------------------------------------------- #
# article
# --------------------------------------------------------------------------- #
class Article(BaseModel):
    """원문 기사 메타데이터."""

    article_id: str
    title: str
    content: str
    published_at: str
    source: str

    model_config = ConfigDict(populate_by_name=True)


# --------------------------------------------------------------------------- #
# claims
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# analysis
# --------------------------------------------------------------------------- #
class KosisSearch(BaseModel):
    """KOSIS 통합검색(statisticsSearch.do) 호출 로그 및 선정 테이블."""

    api: str
    query: str
    params: str
    hits: int
    selected_tbl_id: str | None = None
    selected_tbl_name: str | None = None
    success: int
    error_msg: str | None = None
    duration_ms: int

    model_config = ConfigDict(populate_by_name=True)


class KosisQuery(BaseModel):
    """KOSIS 통계자료(statisticsData.do) 호출 로그."""

    api: str
    tbl_id: str
    params: str
    rows_returned: int
    success: int
    error_msg: str | None = None
    duration_ms: int

    model_config = ConfigDict(populate_by_name=True)


class ClaimAnalysis(BaseModel):
    """주장 1건에 대한 KOSIS 검색·조회 분석 결과."""

    claim_id: str
    kosis_search: KosisSearch
    kosis_query: KosisQuery

    model_config = ConfigDict(populate_by_name=True)


# --------------------------------------------------------------------------- #
# verifications
# --------------------------------------------------------------------------- #
class Evidence(BaseModel):
    """검증 근거 — KOSIS 공식 수치 및 출처 메타데이터."""

    evidence_id: str
    claim_id: str
    source: str
    subject: str
    value: float
    unit: str
    period_type: PeriodType
    period: str
    population: str
    kosis_org_id: str
    kosis_tbl_id: str
    table_name: str
    kosis_item_id: str
    url: str
    classification: dict[str, str] = Field(default_factory=dict)
    last_updated: str
    retrieved_at: str

    model_config = ConfigDict(populate_by_name=True)


class ClaimResult(BaseModel):
    """주장 1건의 검증 판정 결과."""

    claim_id: str
    verdict: str
    verdict_human: str | None = None
    verdict_human_note: str | None = None
    mismatch_type: str | None = None
    claim_value: str
    kosis_value: str
    explanation: str
    confidence: float
    llm_model: str
    evidence: list[Evidence] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class VerificationSummary(BaseModel):
    """기사 단위 검증 요약."""

    total_claims: int
    overall_verdict: str
    average_confidence: float

    model_config = ConfigDict(populate_by_name=True)


class Verifications(BaseModel):
    """검증 요약 + 주장별 판정 결과 묶음."""

    summary: VerificationSummary
    claim_results: list[ClaimResult] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


# --------------------------------------------------------------------------- #
# master record
# --------------------------------------------------------------------------- #
class SlotSchemaMaster(BaseModel):
    """파이프라인 1건 전체 산출물 (slot_schema_master_v2.json 루트)."""

    article: Article
    claims: list[Claim] = Field(default_factory=list)
    analysis: list[ClaimAnalysis] = Field(default_factory=list)
    verifications: Verifications

    model_config = ConfigDict(populate_by_name=True)
