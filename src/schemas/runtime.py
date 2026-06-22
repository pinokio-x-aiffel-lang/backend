"""런타임 스키마 — 파이프라인 1건의 전체 산출물 Pydantic 모델.

기준 문서: docs/slot_schema_master.json
파이프라인 1건의 전체 산출물(article → claims → analysis → verifications)을 표현한다.
도메인 모델 전체를 이 한 파일에 모아두고, 조립 루트는 MasterSchema 다.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PeriodType = Literal["Y", "M", "Q", "S", "D"]


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


class ComparisonSpec(BaseModel):
    """원자 분리된 Claim을 묶고 그룹 수준의 검증 조건을 보관한다.

    같은 compare_id를 가진 Claim들은 동일 원문에서 분리된 비교 대상이다.
    각 Claim의 KOSIS 조회 결과를 모은 뒤 conclusion_type 연산으로
    conclusion_value(conclusion_unit)를 검증한다.
    """

    compare_id: str              # 같은 원문에서 분리된 Claim들의 공유 식별자 (UUID)
    conclusion_type: str         # 검증 연산 (예: "change_rate", "ratio", "comparison")
    conclusion_value: float      # 검증 대상 수치 (예: 15.0)
    conclusion_unit: str         # 단위 (예: "%", "%p", "배")

    model_config = ConfigDict(populate_by_name=True)


class ClaimType(str, Enum):
    """주장의 검증 연산 형태 분류. 값은 WEB_API_CONTRACT §2.3 enum 코드.

    한글 라벨은 프론트(web/src/lib/format.ts CLAIM_TYPE_LABELS)에서 매핑한다.
    우선순위: ABSOLUTE > CHANGE_RATE > RATIO > DISTRIBUTION > COMPARISON > METAPHORIC > VERIFIABLE
    NONE은 7가지 유형 어디에도 해당하지 않는 경우 — 분기 모듈에서 검증대상 없음으로 처리.
    """

    ABSOLUTE = "absolute"          # 절대값 — 단일 시점 값 직접 비교
    CHANGE_RATE = "change_rate"    # 증감률 — (신−구)/구
    RATIO = "ratio"                # 비율 — A/B
    DISTRIBUTION = "distribution"  # 분포 — 구성비/점유율
    COMPARISON = "comparison"      # 비교 — 그룹 간 부등식
    METAPHORIC = "metaphoric"      # 비유비교 — 수치로 표현되나 KOSIS 검증 불가
    VERIFIABLE = "verifiable"      # 검증가능 — KOSIS 검증 가능하나 위 6가지에 미해당 (최후순위)
    NONE = "none"                  # 분류 불가 — 7가지 유형 모두 미해당, 분기에서 제외


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
    compare_conquer: ComparisonSpec | None = None
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
    # CHANGE_RATE(증감) 검증용 — 같은 셀 좌표를 기준 시점(compare_period)으로 한 번 더
    # 조회한 값. value(현재 시점) − compare_value 로 증감을 계산한다([7] compute_change).
    # 절대형/그룹형 claim 이거나 기준 시점 조회 실패면 None.
    compare_value: float | None = None
    compare_period: str | None = None
    # 요청 모집단(population)을 축값에 못 맞춰 '전체(합계)'로 대체했으면 True.
    # → 이 값은 요청 집단이 아닌 전체값이므로 검증 단계가 신뢰도를 낮춰야 한다.
    population_fallback: bool = False
    # population 을 무엇으로 매칭했나: "rule"(규칙+동의어) | "llm"(LLM 폴백).
    match_source: str = "rule"

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
    population_fallback: bool = False  # 모집단 매칭 실패 → 합계 대체 여부
    match_source: str = "rule"         # population 매칭 출처: "rule" | "llm"
    itm_is_rate: bool = False          # 매칭 항목이 변화율(전년동월비 등)인지 — [5] change_rate 처리용
    error: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class Verdict(str, Enum):
    """검증 판정 코드 (WEB_API_CONTRACT §2.6). MetricResult/ClaimResult 공용."""

    TRUE = "T"               # 일치 — 수치 + 기사 해석 모두 정확
    FALSE = "F"              # 불일치 — 수치 자체를 잘못 인용(확정 가짜); [8] 통과
    NEEDS_REVIEW = "M"       # 기사의 수치 오도/왜곡 — [8] check_alignment 만 생성
    NOT_ENOUGH_INFO = "N"    # NEI: 무증거·비교불가·검증대상 아님·정합성 판정 실패 (코드 N 유지)


class MismatchType(str, Enum):
    """verdict=F/M 사유 분류 (MetricResult.mismatch_type).

    magnitude/rounding/direction 은 수치 비교([7]), unit/period/population/
    subject/aggregation 은 정합성([8]) 영역.
    """

    MAGNITUDE = "magnitude"      # 값 크기 차이(허용오차 크게 초과)
    ROUNDING = "rounding"        # 허용오차 소폭 초과(반올림 경계)
    DIRECTION = "direction"      # 증감 방향 차이(부호/그룹)
    UNIT = "unit"                # 단위 불일치·비교불가
    PERIOD = "period"            # 기간 불일치
    POPULATION = "population"    # 모집단 불일치(예: 전체↔청년)
    SUBJECT = "subject"          # 측정 주제 불일치
    AGGREGATION = "aggregation"  # 집계 방식 불일치(평균↔합계 등)


class HitlCategory(str, Enum):
    """HITL(사람 검토) 사유 분류 (ClaimResult.hitl_category).

    needs_hitl=True 인 건의 라우팅 기준. 두 사유는 다운스트림 처리가 다르다:
    데이터 모호는 라벨러 판단(재시도 무의미), 시스템 장애는 재시도/운영 대상.
    """

    DATA_AMBIGUITY = "data_ambiguity"   # [7] 1위 표 불일치인데 다른 표에 근사값 → 라벨러 판단
    SYSTEM_FAILURE = "system_failure"   # [8] 정합성 LLM 판정 실패(네트워크/파싱) → 재시도/운영


class MetricResult(BaseModel):
    """[7] calculate_metric — 주장 수치 ↔ KOSIS 공식 수치 비교 결과.

    ClaimAnalysis.metric 에 claim 1건 단위로 담긴다(키는 부모 ClaimAnalysis.claim_id).
    ABSOLUTE 는 claim_value 와 kosis_value(=evidence.value)를 직접 비교한다.
    change_rate/ratio 등 그룹 연산은 같은 compare_id 의 evidence 들을 묶어
    computed_value 를 산출(대표 claim 의 analysis 에 보관) — 현재 미배선(TODO).
    decide_verdict([9]) 가 verdict/confidence 를, generate_explanation([10]) 이
    설명을 이 결과로 조립한다.
    """

    operation: str                        # 사용 연산 (claim_type; 그룹이면 conclusion_type)
    claim_value: float | None = None      # 주장이 말한 수치
    kosis_value: float | None = None      # 비교 기준 공식 수치 (ABSOLUTE = evidence.value)
    rel_diff: float | None = None         # |주장−기준| / |기준| → decide_verdict 가 confidence 로 매핑
    within_tolerance: bool | None = None  # 허용오차 내 일치 여부
    verdict: Verdict | None = None        # [7] T/F/NEI 초기, [8] T→T/M/NEI 보정
    mismatch_type: MismatchType | None = None  # verdict=F/M 사유
    note: str | None = None               # [7] 계산 비고 (단위환산·폴백·비교불가 사유)
    # ── [8] check_alignment 판정 근거 ──
    align_reason: str | None = None       # 정합성 판정 사유 (LLM reason / 실패 사유)
    align_source: str | None = None       # 판정 출처: "llm" | "llm_failed"
    # ── 그룹 비교용(현재 미배선) ──
    compare_id: str | None = None         # 같은 원문에서 분리된 비교 그룹; ABSOLUTE 단건이면 None
    computed_value: float | None = None   # 그룹 연산 산출값(change_rate 등); ABSOLUTE 면 None

    model_config = ConfigDict(populate_by_name=True)


class ClaimAnalysis(BaseModel):
    """주장 1건에 대한 KOSIS 검색·조회 분석 결과."""

    claim_id: str
    kosis_search: KosisSearch
    candidates: list[KosisCandidate] = Field(default_factory=list)  # [4] 상위 N개 후보 풀
    cell_attempts: list[CellAttempt] = Field(default_factory=list)  # [5] 후보 표별 조회 시도(디버깅)
    kosis_query: KosisQuery
    # [5] 매칭된 모든 후보 셀(RANK 순). [6]이 1위 적합 표를 evidences[0]으로 정렬,
    # [7] calculate_metric 이 evidences[0]부터 origin 과 비교한다.
    evidences: list[Evidence] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class ClaimResult(BaseModel):
    """주장 1건의 검증 판정 결과.

    [7] calculate_metric 이 생성하고 metric/표시필드를 시드 → [8] check_alignment 가
    metric 보정 → [9] decide_verdict 가 verdict/confidence/요약 확정 → [10]이 explanation.
    진행 중 미완성 허용을 위해 상위 필드는 기본값을 둔다(단계별 점진 채움).
    """

    claim_id: str
    verdict: str = "UNVERIFIED"
    verdict_human: str | None = None
    verdict_human_note: str | None = None
    mismatch_type: str | None = None
    claim_value: str = ""
    kosis_value: str | None = None  # KOSIS 조회 실패/미조회 시 None (더미값 금지)
    explanation: str = ""
    confidence: float = 0.0
    llm_model: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    metric: MetricResult | None = None  # [7] 비교 결과([8]이 보정). 미계산 시 None
    # HITL 라우팅: [7] 데이터 모호 / [8] 정합성 LLM 판정 실패(시스템 장애) 시 사람 검토 필요.
    needs_hitl: bool = False
    hitl_category: HitlCategory | None = None  # 사유 분류(라우팅 기준); hitl_reason 은 사람용 설명
    hitl_reason: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class VerificationSummary(BaseModel):
    """기사 단위 검증 요약."""

    total_claims: int
    # claim별 verdict 분포 카운트 {"T":..,"F":..,"M":..,"N":..}. 비율은 프론트가
    # total_claims 로 나눠 도출(카운트가 원본, 비율은 파생). 옛 overall_verdict(단일 라벨) 대체.
    verdict_counts: dict[str, int] = Field(default_factory=dict)
    # 기사 사실성: T / (T+F+M). N(검증 불가) 제외 — '검증된 것 중 사실' 비율.
    overall_confidence: float = 0.0
    # 검증률: (T+F+M) / total_claims. 우리가 실제 검증해낸 비율(N=미검증).
    coverage: float = 0.0
    # [10] generate_explanation 이 claim별 결과를 종합해 LLM 으로 생성하는 기사 단위 총평.
    # LLM 실패 시 결정적 템플릿 총평으로 폴백한다. 미생성 시 "".
    overall_opinion: str = ""

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
    sentences: list[str] = Field(default_factory=list)  # 검증 단위 원자 문장 ([2]에서 적재)
    claims: list[Claim] = Field(default_factory=list)
    analysis: list[ClaimAnalysis] = Field(default_factory=list)
    verifications: Verifications | None = None

    model_config = ConfigDict(populate_by_name=True)
