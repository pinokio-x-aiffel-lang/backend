import asyncio
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


_STEPS = [
    "기사 내용 확인",
    "클레임 추출",
    "KOSIS 통계표 찾기",
    "KOSIS 조회",
    "한국어 수사 산술로 변환",
    "통계 수치 비교 판단",
    "통계수치와 문장의 정합성 판단",
    "종합 분석",
    "설명 생각",
    "검증 결과 생성",
]


async def run_pipeline_with_queue(q: asyncio.Queue, content: str) -> None:
    try:
        for i, step_name in enumerate(_STEPS, 1):
            t0 = time.monotonic()
            await asyncio.sleep(1)  # TODO: 실제 단계별 작업으로 교체
            duration_ms = int((time.monotonic() - t0) * 1000)
            await q.put({
                "event": "step",
                "data": {
                    "step": i,
                    "name": step_name,
                    "status": "done",
                    "duration_ms": duration_ms,
                },
            })

        result = await verify_article(VerifyRequest(content=content))
        await q.put({"event": "result", "data": result.model_dump()})
    except Exception as e:
        await q.put({"event": "error", "data": {"message": str(e)}})
    finally:
        await q.put(None)


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

    return VerifyResponse(
        article=article,
        claims=claims,
        verifications=verifications,
    )
