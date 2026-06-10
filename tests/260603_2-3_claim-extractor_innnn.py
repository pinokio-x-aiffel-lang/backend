"""extract_statistical_claims + normalize_claim 모듈 단위 테스트.

대상 모듈: extract_statistical_claims, normalize_claim
작성자: innnn <innnn712@gmail.com>
작성일: 2026-06-03
"""
import pytest

from src.modules.extract_statistical_claims import extract_statistical_claims
from src.modules.normalize_claim import normalize_claim
from src.schemas.runtime import Article, MasterSchema

_VALID_PERIOD_TYPES = {"Y", "M", "Q", "D"}


def _make_record(article_id: str = "art-0001", content: str = "2024년 합계출산율은 0.72명이다.") -> MasterSchema:
    return MasterSchema(
        article=Article(
            article_id=article_id,
            title="테스트 기사",
            content=content,
            published_at="2024-01-01",
            source="테스트",
        )
    )


# ------------------------------------------------------------------ #
# 실제 기사 픽스처
# ------------------------------------------------------------------ #
_SEONGSIMDANG = """\
대전의 명물 빵집 '성심당'이 지난해 사상 최대 매출액을 기록했다.
매장이 10여 개에 불과한 지역 기반 빵집이지만, 뚜레쥬르 같은 대형 프랜차이즈 빵집보다 2년 연속 더 많은 이익을 냈다.
5일 금융감독원에 따르면 성심당의 작년 매출액은 1937억6000만원으로, 전년(1243억원) 대비 56%나 늘어났다.
같은 기간 영업이익은 478억원을 기록하며 전년(315억원)보다 50% 증가했다.
2020년 488억원이었던 매출액은 2021년 628억원, 2022년 817억원을 기록했다.
2023년에는 1243억원의 매출을 찍으며 프랜차이즈가 아닌 단일 빵집 브랜드 매출로는 최초로 1000억원 선을 넘었다.
작년 말 기준 성심당의 매장 수는 16곳, 뚜레쥬르는 1300여 곳이다.
"""

_MANUFACTURING_EMPLOYMENT = """\
지난달 제조업 취업자 수가 12년 만에 최저치로 떨어졌다.
16일 통계청에 따르면, 지난달 전체 취업자 수는 2787만8000명으로 1년 전 대비 13만5000명 늘었다.
제조업 분야 취업자 수는 5만6000명 줄어든 439만6000명으로 집계됐다.
1월 기준 2013년 이후 12년 만의 최저치다.
지난달 도소매 취업자 수는 1년 전보다 9만1000명 줄어든 318만3000명으로, 역대 최저다.
건설업 취업자 수도 1년 새 16만9000명이나 줄어, 2013년 이후 가장 큰 낙폭을 기록했다.
KDI는 올 한 해 취업자 수 증가 폭이 작년(15만9000명)보다 6만명 가까이 적은 10만명에 그칠 것이라고 전망했다.
"""

_COUPANG_FINE = """\
작년 이커머스 기업 쿠팡의 '알고리즘 조작 의혹' 사건을 맡아 1600억원 넘는 과징금 부과를 이끌어낸 공정거래위원회 조사팀이 '2024년 올해의 공정인상'을 받았다.
공정위는 지난 8월 쿠팡의 공정거래법 위반 혐의에 대해 과징금 1628억원을 부과했다.
쿠팡은 알고리즘 조작으로 PB 상품과 직매입 상품 등 자사 상품 6만여 종의 쿠팡 랭킹 순위를 부당하게 높였다는 혐의를 받는다.
쿠팡 임직원 2000여 명을 동원해 PB 상품에 임직원 후기를 최소 7만여 건 단 혐의도 있다.
공정위는 이 사건을 2021년부터 약 3년 간 조사해서 작년 위법하다고 결론냈다.
"""


# ------------------------------------------------------------------ #
# extract_statistical_claims
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_extract_populates_claims():
    record = _make_record()
    assert record.claims == []

    await extract_statistical_claims(record)

    assert len(record.claims) >= 1


@pytest.mark.asyncio
async def test_extract_claim_fields():
    record = _make_record("art-0042")
    await extract_statistical_claims(record)

    claim = record.claims[0]
    assert claim.claim_id
    assert claim.article_id == "art-0042"
    assert claim.sentence
    assert claim.subject
    assert claim.unit
    assert claim.period_type in {"Y", "M", "Q", "D"}


@pytest.mark.asyncio
async def test_extract_value_slot_raw_not_empty():
    record = _make_record()
    await extract_statistical_claims(record)

    for claim in record.claims:
        assert claim.value.raw, "value.raw 가 비어 있으면 안 됨"
        assert claim.period_value.raw, "period_value.raw 가 비어 있으면 안 됨"


# ------------------------------------------------------------------ #
# 실제 기사 테스트 (HCX-003 실호출)
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_extract_seongsimdang():
    """성심당 매출·영업이익 기사 — 수치 클레임 3개 이상, 슬롯 검증."""
    record = _make_record("RY3AUBJSBRHJXJEHCIKY43YOWU", _SEONGSIMDANG)
    await extract_statistical_claims(record)

    assert len(record.claims) >= 3
    for claim in record.claims:
        assert claim.sentence
        assert claim.value.raw and claim.value.raw != ""
        assert claim.period_type in _VALID_PERIOD_TYPES


@pytest.mark.asyncio
async def test_extract_manufacturing_employment():
    """제조업 취업자 수 기사 — 취업자·감소폭 수치 클레임 다수 추출."""
    record = _make_record("S73YKZJAG5G6RMIWCEKFVLGH2Q", _MANUFACTURING_EMPLOYMENT)
    await extract_statistical_claims(record)

    assert len(record.claims) >= 4
    for claim in record.claims:
        assert claim.sentence
        assert claim.value.raw and claim.value.raw != ""
        assert claim.period_type in _VALID_PERIOD_TYPES


@pytest.mark.asyncio
async def test_extract_coupang_fine():
    """쿠팡 과징금 기사 — 금액·건수 클레임 추출, subject 비어있지 않음."""
    record = _make_record("FSUZ5SCJ4ZFA5E6KTUPNLHXJSU", _COUPANG_FINE)
    await extract_statistical_claims(record)

    assert len(record.claims) >= 2
    for claim in record.claims:
        assert claim.sentence
        assert claim.subject and claim.subject != ""
        assert claim.value.raw and claim.value.raw != ""


# ------------------------------------------------------------------ #
# normalize_claim
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_normalize_fills_llm_value():
    record = _make_record()
    await extract_statistical_claims(record)
    await normalize_claim(record)

    for claim in record.claims:
        assert claim.value.llm_value != "", "value.llm_value 가 채워져야 함"
        assert claim.period_value.llm_value != "", "period_value.llm_value 가 채워져야 함"


@pytest.mark.asyncio
async def test_normalize_no_claims_is_noop():
    """claims 가 빈 record 에서 normalize 를 호출해도 예외 없이 통과해야 한다."""
    record = _make_record()
    assert record.claims == []
    await normalize_claim(record)  # 예외 없으면 OK
