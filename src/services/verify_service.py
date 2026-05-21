import time
from src.schemas.verify import (
    Article,
    Claim,
    ClaimInfo,
    ClaimResult,
    Evidence,
    VerificationSummary,
    Verifications,
    VerifyRequest,
    VerifyResponse,
)


async def verify_article(request: VerifyRequest) -> VerifyResponse:
    """
    실제 검증 파이프라인을 연결하기 전까지 사용하는 임시 서비스 함수.

    나중에는 이 함수 안에서:
    1. 기사 URL/본문 판별
    2. 기사 파싱
    3. claim detection
    4. claim extraction
    5. KOSIS 검색
    6. numeric layer 비교
    7. report generation
    을 호출하면 된다.
    """

    article = Article(
        title=None,
        source=None,
        published_at=None,
        content=request.content,
    )

    claims = [
        Claim(
            claim_id="sample_c01",
            sentence="통계청에 따르면 2024년 합계출산율은 0.72명이다.",
            claim_info=ClaimInfo(
                subject="합계출산율",
                claim_type="규모",
                claim_value="0.72",
                normalized_value="0.72",
                unit="명",
                period="2024",
                compare_period=None,
                population="전국",
                cited_source="통계청",
            ),
        )
    ]

    evidence = [
        Evidence(
            source="KOSIS",
            subject="합계출산율",
            value="0.72",
            unit="명",
            period="2024",
            population="전국",
            table_name="출생아수, 합계출산율, 자연증가 등",
            url="https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1B8000F",
            last_updated="2025-02-26",
        )
    ]

    claim_results = [
        ClaimResult(
            claim_id="sample_c01",
            verdict="T",
            mismatch_type=None,
            claim_value="0.72",
            kosis_value="0.72",
            explanation="기사의 2024년 합계출산율 0.72명은 KOSIS 공식 수치와 일치합니다.",
            confidence=0.97,
            evidence=evidence,
        )
    ]

    verifications = Verifications(
        summary=VerificationSummary(
            total_claims=len(claims),
            overall_verdict="T",
            average_confidence=0.97,
            overview_reason="검증 대상 통계 주장이 공식 통계와 일치합니다.",
        ),
        claim_results=claim_results,
    )

    print("- 실제 검증 파이프라인을 실행합니다.")
    time.sleep(1)
    print("- 클레임 추출중")
    time.sleep(1)
    print("- KOSIS 조회중")
    time.sleep(1)

    return VerifyResponse(
        article=article,
        claims=claims,
        verifications=verifications,
    )
