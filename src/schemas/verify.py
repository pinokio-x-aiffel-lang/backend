from pydantic import BaseModel, Field


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
    value: str
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
