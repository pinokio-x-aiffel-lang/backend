from __future__ import annotations

from pydantic import BaseModel, Field

from src.schemas.runtime import MasterSchema


class VerifyRequest(BaseModel):
    content: str = Field(
        ...,
        description="기사 URL 또는 기사 본문 텍스트",
        examples=["통계청에 따르면 2024년 합계출산율은 0.72명이다."]
    )


class Article(BaseModel):
    title: str | None = None
    source: str | None = None
    published_at: str | None = None
    content: str


class ClaimInfo(BaseModel):
    subject: str
    claim_type: str
    claim_value: str
    normalized_value: str | None = None
    unit: str | None = None
    period: str | None = None
    compare_period: str | None = None
    population: str | None = None
    cited_source: str | None = None


class Claim(BaseModel):
    claim_id: str
    sentence: str
    claim_info: ClaimInfo


class Evidence(BaseModel):
    source: str
    subject: str
    value: str | None = None
    unit: str | None = None
    period: str | None = None
    population: str | None = None
    table_name: str | None = None
    url: str | None = None
    last_updated: str | None = None


class VerificationSummary(BaseModel):
    total_claims: int
    overall_verdict: str
    average_confidence: float
    overview_reason: str


class ClaimResult(BaseModel):
    claim_id: str
    verdict: str
    mismatch_type: str | None = None
    claim_value: str | None = None
    kosis_value: str | None = None
    explanation: str
    confidence: float
    evidence: list[Evidence] = []


class Verifications(BaseModel):
    summary: VerificationSummary
    claim_results: list[ClaimResult]


class VerifyResponse(BaseModel):
    article: Article
    claims: list[Claim]
    verifications: Verifications


# ─────────────────────────────────────────────────────────────────────────────
# MasterSchema(런타임) → VerifyResponse(HTTP 경계 DTO) 매핑
#   파이프라인 내부는 MasterSchema로 흐르고, 프론트로 나갈 때만 여기서 변환한다.
# ─────────────────────────────────────────────────────────────────────────────
_VERDICT_MAP = {
    "T": "T", "TRUE": "T",
    "F": "F", "FALSE": "F",
    "M": "M", "MISLEADING": "M",
    "NEI": "NEI", "UNVERIFIED": "NEI",
}
_VERDICT_ORDER = ["T", "F", "M", "NEI"]


def _verdict_code(raw: str | None) -> str:
    """런타임 verdict 문자열 → 프론트 enum(T/F/M/NEI). 미상은 NEI."""
    return _VERDICT_MAP.get(str(raw or "").strip().upper(), "NEI")


def _overall_verdict(codes: list[str]) -> str:
    """claim별 코드 집합 → 조합 코드(T/F/M/NEI 순). 비면 NEI."""
    present = [c for c in _VERDICT_ORDER if c in set(codes)]
    return "+".join(present) if present else "NEI"


def to_verify_response(master_schema: MasterSchema) -> VerifyResponse:
    """완성된 MasterSchema를 프론트 계약(VerifyResponse)으로 변환."""
    if master_schema.article is None or master_schema.verifications is None:
        raise ValueError("완성되지 않은 master_schema는 VerifyResponse로 변환할 수 없습니다.")

    article = Article(
        title=master_schema.article.title,
        source=master_schema.article.source,
        published_at=master_schema.article.published_at,
        content=master_schema.article.content,
    )

    claims = [
        Claim(
            claim_id=c.claim_id,
            sentence=c.sentence,
            claim_info=ClaimInfo(
                subject=c.subject,
                claim_type=c.claim_type,
                claim_value=c.value.raw,
                normalized_value=c.value.llm_value or None,
                unit=c.unit,
                period=c.period_value.llm_value or c.period_value.raw,
                compare_period=(
                    c.compare_period_value.llm_value if c.compare_period_value else None
                ),
                population=c.population,
                cited_source=c.cited_source,
            ),
        )
        for c in master_schema.claims
    ]

    codes: list[str] = []
    claim_results: list[ClaimResult] = []
    for r in master_schema.verifications.claim_results:
        code = _verdict_code(r.verdict)
        codes.append(code)
        claim_results.append(
            ClaimResult(
                claim_id=r.claim_id,
                verdict=code,
                mismatch_type=r.mismatch_type,
                claim_value=r.claim_value,
                kosis_value=r.kosis_value,
                explanation=r.explanation,
                confidence=r.confidence,
                evidence=[
                    Evidence(
                        source=e.source,
                        subject=e.subject,
                        value=str(e.value) if e.value is not None else None,
                        unit=e.unit,
                        period=e.period,
                        population=e.population,
                        table_name=e.table_name,
                        url=e.url,
                        last_updated=e.last_updated,
                    )
                    for e in r.evidence
                ],
            )
        )

    s = master_schema.verifications.summary
    summary = VerificationSummary(
        total_claims=s.total_claims,
        overall_verdict=_overall_verdict(codes),
        average_confidence=s.average_confidence,
        overview_reason=f"총 {s.total_claims}건의 주장을 분석했습니다.",
    )

    return VerifyResponse(
        article=article,
        claims=claims,
        verifications=Verifications(summary=summary, claim_results=claim_results),
    )
