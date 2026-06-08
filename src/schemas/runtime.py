"""런타임 스키마 — 파이프라인 1건의 전체 산출물 Pydantic 모델.

기준 문서: docs/slot_schema_master.json
파이프라인 1건의 전체 산출물(article → claims → analysis → verifications)을 표현한다.
도메인 모델 전체를 이 한 파일에 모아두고, 조립 루트는 MasterSchema 다.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PeriodType = Literal["Y", "M", "Q", "D"]


# --------------------------------------------------------------------------- #
# article
# --------------------------------------------------------------------------- #
class Article(BaseModel):
    """원문 기사 메타데이터."""

    article_id: str
    title: str | bool | None = None
    content: str
    published_at: str | bool | None = None
    source: str | bool | None = None
    url: str | None = None

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


class CompareGroup(BaseModel):
    """동일 비교 대상을 묶는 그룹 식별자. 같은 compare_id끼리 비교군이다."""

    compare_id: int

    model_config = ConfigDict(populate_by_name=True)


class ClaimType(str, Enum):
    """주장의 검증 연산 형태 분류. 값은 WEB_API_CONTRACT §2.3 enum 코드.

    한글 라벨은 프론트(web/src/lib/format.ts CLAIM_TYPE_LABELS)에서 매핑한다.
    """

    ABSOLUTE = "absolute"          # 절대값 — 단일 시점 값 직접 비교
    CHANGE_RATE = "change_rate"    # 증감률 — (신−구)/구
    RATIO = "ratio"                # 비율 — A/B
    DISTRIBUTION = "distribution"  # 분포 — 구성비/점유율
    COMPARISON = "comparison"      # 비교 — 그룹 간 부등식
    METAPHORIC = "metaphoric"      # 정성/추상 — 수치 검증 불가
    OTHER = "other"                # 예외 — 6개 연산 유형에 안 맞는 분류 fallback


class Claim(BaseModel):
    """기사 한 문장에서 추출된 수치 기반 사실 주장."""

    claim_id: str
    article_id: str
    sentence: str
    claim_type: ClaimType
    subject: str
    value: ValueSlot
    unit: str
    aggregation: str
    period_type: PeriodType
    period_value: ValueSlot
    compare_period_value: ValueSlot | None = None
    compare_group: CompareGroup | None = None
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


class KosisCandidate(BaseModel):
    """KOSIS 통합검색 후보 통계표 한 건 (selected 이전의 상위 N개 풀).

    src.kosis.search.SearchHit 의 핵심 필드만 추린 직렬화 표현(raw 제외).
    selected_tbl_id 선정은 이후 단계의 몫이고, 이 목록은 그 선정 풀이다.
    """

    org_id: str
    tbl_id: str
    tbl_nm: str
    org_nm: str = ""
    stat_nm: str = ""           # 통계(조사)명
    prd_de: str = ""            # 수록 기간 (STRT_PRD_DE~END_PRD_DE)

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


class Evidence(BaseModel):
    """검증 근거 — KOSIS 공식 수치 및 출처 메타데이터.

    KOSIS 조회([4]~[7])로 채워지는 필드는 조회 전이면 값이 없으므로 None 허용
    (더미값을 내보내지 않는다). [5] fetch_kosis_data 가 ClaimAnalysis.evidence 에
    선정 셀을 담고, 이후 단계가 verifications 로 옮긴다.
    """

    claim_id: str
    source: str
    subject: str
    unit: str
    period_type: PeriodType
    period: str
    population: str
    # KOSIS 조회로 채워지는 필드 — 미조회 시 None
    evidence_id: str | None = None
    value: float | None = None
    kosis_org_id: str | None = None
    kosis_tbl_id: str | None = None
    table_name: str | None = None
    kosis_item_id: str | None = None
    url: str | None = None
    classification: dict[str, str] = Field(default_factory=dict)
    last_updated: str | None = None
    retrieved_at: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class CellAttempt(BaseModel):
    """[5] 후보 표 1개에 대한 셀 조회 시도 결과 (디버깅·표시용).

    표가 가진 항목(items)·분류축(axes)과 subject/population 매칭 결과를 담는다.
    매칭 실패 사유(error)로 '왜 못 찾았는지'를 파악한다.
    """

    tbl_id: str
    tbl_nm: str
    matched: bool = False
    value: float | None = None
    unit: str | None = None
    itm_id: str | None = None
    items: list[str] = Field(default_factory=list)            # 표 항목명(ITM_NM) 샘플
    axes: dict[str, list[str]] = Field(default_factory=dict)  # 분류축명 → 값명 샘플
    error: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class ClaimAnalysis(BaseModel):
    """주장 1건에 대한 KOSIS 검색·조회 분석 결과."""

    claim_id: str
    kosis_search: KosisSearch
    candidates: list[KosisCandidate] = Field(default_factory=list)  # [4] 상위 N개 후보 풀
    cell_attempts: list[CellAttempt] = Field(default_factory=list)  # [5] 후보 표별 조회 시도(디버깅)
    kosis_query: KosisQuery
    evidence: Evidence | None = None  # [5] 선정 셀(공식 수치). 미조회/실패 시 None

    model_config = ConfigDict(populate_by_name=True)


class ClaimResult(BaseModel):
    """주장 1건의 검증 판정 결과."""

    claim_id: str
    verdict: str
    verdict_human: str | None = None
    verdict_human_note: str | None = None
    mismatch_type: str | None = None
    claim_value: str
    kosis_value: str | None = None  # KOSIS 조회 실패/미조회 시 None (더미값 금지)
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
class MasterSchema(BaseModel):
    """파이프라인 1건 전체 산출물 (docs/slot_schema_master.json 루트).

    파이프라인을 직접 흐르는 스키마. 진행 중에는 단계들이 필드를 순차적으로
    채우므로 상위 필드는 Optional(미완성 허용)이다. `content`는 원본 입력으로,
    흐르되 직렬화(model_dump)에는 포함하지 않는다(exclude=True).
    """

    content: str | None = Field(default=None, exclude=True)  # 원본 입력 (URL/본문)
    article: Article | None = None
    claims: list[Claim] = Field(default_factory=list)
    analysis: list[ClaimAnalysis] = Field(default_factory=list)
    verifications: Verifications | None = None

    model_config = ConfigDict(populate_by_name=True)
