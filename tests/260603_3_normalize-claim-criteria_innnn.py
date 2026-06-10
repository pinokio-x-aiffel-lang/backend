"""normalize_claim 기준 테스트 — 표 6개 대분류 전 항목 커버.

현재 구현은 TODO 스텁(value="0.72", period="2024")이므로
대부분 FAIL 이 예상됨. 구현 완성 후 전 케이스 PASS 를 목표로 한다.

expected 값 규약:
  - 정수/실수: 문자열 형태 "230000", "0.32"
  - 근사(③):  numeric 핵심값이 llm_value 에 포함되는지 in 검사
  - 범위(④):  ">=100" / "<=100" / ">100" / "<100" / "50~100" 형식
  - 증감(⑤):  부호+수치 "+3.2" / "-5" / "%p" 포함 검사
  - 배수(⑤):  곱셈값 "2.0" / "0.5"

대상 모듈: normalize_claim
작성자: innnn <innnn712@gmail.com>
작성일: 2026-06-03
"""
import pytest

from src.modules.normalize_claim import normalize_claim
from src.schemas.runtime import Article, Claim, ClaimType, MasterSchema, ValueSlot


# ------------------------------------------------------------------ #
# helpers
# ------------------------------------------------------------------ #
def _vs(raw: str) -> ValueSlot:
    return ValueSlot(raw=raw, llm_value="", is_inferred=False)


def _make(value_raw: str, period_raw: str = "2024년", unit: str = "명") -> MasterSchema:
    claim = Claim(
        claim_id="c-0001",
        article_id="art-0001",
        sentence=f"테스트: {value_raw}",
        claim_type=ClaimType.NONE,
        subject="테스트",
        value=_vs(value_raw),
        unit=unit,
        aggregation="일반",
        period_type="Y",
        period_value=_vs(period_raw),
        population="전국",
        cited_source="KOSIS",
    )
    return MasterSchema(
        article=Article(
            article_id="art-0001",
            title="테스트",
            content="테스트",
            published_at="2024-01-01",
            source="테스트",
        ),
        claims=[claim],
    )


def _val(record: MasterSchema) -> str:
    return record.claims[0].value.llm_value


def _period(record: MasterSchema) -> str:
    return record.claims[0].period_value.llm_value


# ================================================================== #
# ① 수 읽기 체계
# ================================================================== #

# -- 한자어 수사 --
@pytest.mark.asyncio
@pytest.mark.parametrize("raw,expected", [
    ("일",     "1"),
    ("이",     "2"),
    ("삼",     "3"),
    ("십",     "10"),
    ("이십",   "20"),
    ("삼십이", "32"),
    ("백",     "100"),
    ("천이백", "1200"),
    ("오천",   "5000"),
])
async def test_sino_korean_numeral(raw, expected):
    r = _make(raw)
    await normalize_claim(r)
    assert _val(r) == expected, f"한자어 '{raw}' → 기대 '{expected}', 실제 '{_val(r)}'"


# -- 고유어 수사 --
@pytest.mark.asyncio
@pytest.mark.parametrize("raw,expected", [
    ("하나",   "1"),
    ("둘",     "2"),
    ("셋",     "3"),
    ("넷",     "4"),
    ("다섯",   "5"),
    ("열",     "10"),
    ("열다섯", "15"),
    ("스물",   "20"),
    ("스물셋", "23"),
    ("서른",   "30"),
    ("마흔",   "40"),
    ("쉰",     "50"),
    ("예순",   "60"),
    ("일흔",   "70"),
    ("여든",   "80"),
    ("아흔",   "90"),
])
async def test_native_korean_numeral(raw, expected):
    r = _make(raw)
    await normalize_claim(r)
    assert _val(r) == expected, f"고유어 '{raw}' → 기대 '{expected}', 실제 '{_val(r)}'"


# -- 관형형 변화 --
# [① 관형사형 수사] 한/두/세/스무 같은 관형사형 수사는 정규화 미지원 — 의도적 미체크(skip).
#   _parse_native 는 고유어 수사(하나/둘/스물)만 처리. 필요해지면 _NATIVE 관형사 매핑을
#   살려 켤 것. (2026-06 팀 결정: 현재 스코프 제외)
@pytest.mark.skip(reason="① 관형사형 수사(한/두/세/스무) 미지원 — 의도적 미체크")
@pytest.mark.asyncio
@pytest.mark.parametrize("raw,expected", [
    ("한 명",  "1"),
    ("두 명",  "2"),
    ("세 명",  "3"),
    ("스무 명","20"),
])
async def test_native_korean_determiner(raw, expected):
    r = _make(raw)
    await normalize_claim(r)
    assert _val(r) == expected, f"관형형 '{raw}' → 기대 '{expected}', 실제 '{_val(r)}'"


# ================================================================== #
# ② 큰 수 단위
# ================================================================== #

@pytest.mark.asyncio
@pytest.mark.parametrize("raw,expected", [
    # 단순 단위
    ("1만",           "10000"),
    ("23만",          "230000"),
    ("1억",           "100000000"),
    ("1조",           "1000000000000"),
    # 보조단위 조합
    ("2천",           "2000"),
    ("3백",           "300"),
    ("2천억",         "200000000000"),
    ("5천만",         "50000000"),
    # 복합 큰 수
    ("1조 2천억",     "1200000000000"),
    ("3억 5천만",     "350000000"),
    ("2억 3백만",     "203000000"),
    # 아라비아+단위 혼합
    ("23만 명",       "230000"),
    ("1,200억",       "120000000000"),
    ("3.2억",         "320000000"),
    ("0.72",          "0.72"),    # 소수점 그대로
])
async def test_large_number_units(raw, expected):
    r = _make(raw)
    await normalize_claim(r)
    assert _val(r) == expected, f"큰 수 '{raw}' → 기대 '{expected}', 실제 '{_val(r)}'"


# ================================================================== #
# ③ 근사·불확실  ⚠
# ================================================================== #

@pytest.mark.asyncio
@pytest.mark.parametrize("raw,core", [
    # 근사(약·대략류): 수치 핵심값이 llm_value 에 포함되어야 함
    ("약 23만",       "230000"),
    ("대략 100",      "100"),
    ("100가량",       "100"),
    ("23만 쯤",       "230000"),
    ("얼추 1억",      "100000000"),
    # 안팎·내외
    ("100명 안팎",    "100"),
    ("5% 내외",       "5"),
    # 초과형
    ("100여 명",      "100"),
    # [① 관형사형 수사] "한"(관형사) 미지원 → 의도적 미체크(skip)
    pytest.param("한 시간 남짓", "1", marks=pytest.mark.skip(
        reason="① 관형사형 수사('한') 미지원 — 의도적 미체크")),
    ("1만 가까이",    "10000"),
])
async def test_approximate_value_contains_core(raw, core):
    """근사 표현은 정확값 아님 — 핵심 수치가 llm_value 에 포함되는지만 검증."""
    r = _make(raw)
    await normalize_claim(r)
    assert core in _val(r), f"근사 '{raw}' → 핵심값 '{core}'이 '{_val(r)}'에 없음"


# ================================================================== #
# ④ 범위·한계  ⚠
# ================================================================== #

@pytest.mark.asyncio
@pytest.mark.parametrize("raw,expected", [
    # 포함 경계
    ("100 이상",         ">=100"),
    ("50 이하",          "<=50"),
    # 배타 경계
    ("100 초과",         ">100"),
    ("50 미만",          "<50"),
    # 구간
    ("50부터 100까지",   "50~100"),
    ("50~100",           "50~100"),
    # 극값
    ("최대 100",         "<=100"),
    ("최소 50",          ">=50"),
    ("최고 100",         "<=100"),
    ("최저 50",          ">=50"),
])
async def test_range_and_limits(raw, expected):
    r = _make(raw)
    await normalize_claim(r)
    assert _val(r) == expected, f"범위 '{raw}' → 기대 '{expected}', 실제 '{_val(r)}'"


# ================================================================== #
# ⑤ 증감·변화  ⚠
# ================================================================== #

# -- 방향 --
@pytest.mark.asyncio
@pytest.mark.parametrize("raw,sign", [
    ("3.2% 증가",  "+"),
    ("5% 감소",    "-"),
    ("10% 상승",   "+"),
    ("2% 하락",    "-"),
    ("생산량 증가", "+"),
    ("수출 감소",  "-"),
])
async def test_change_direction(raw, sign):
    r = _make(raw)
    await normalize_claim(r)
    assert _val(r).startswith(sign), f"방향 '{raw}' → 부호 '{sign}', 실제 '{_val(r)}'"


# -- 변화율 --
@pytest.mark.asyncio
@pytest.mark.parametrize("raw,expected", [
    ("3.2% 증가", "+3.2"),
    ("5% 감소",   "-5.0"),
    ("10% 상승",  "+10.0"),
])
async def test_change_rate(raw, expected):
    r = _make(raw)
    await normalize_claim(r)
    assert _val(r) == expected, f"변화율 '{raw}' → 기대 '{expected}', 실제 '{_val(r)}'"


# -- 퍼센트포인트 (단위는 extract 가 unit 으로 분리; normalize 는 부호+수치만) --
@pytest.mark.asyncio
@pytest.mark.parametrize("raw,expected", [
    ("3%p 상승",          "+3.0"),
    ("2%p 하락",          "-2.0"),
    ("1.5퍼센트포인트 증가", "+1.5"),
])
async def test_percentage_point_unit(raw, expected):
    """%p 구분은 unit(=%p)이 보유. normalize 는 value 를 부호+수치로 두고 unit 보존."""
    r = _make(raw, unit="%p")
    await normalize_claim(r)
    assert _val(r) == expected, f"%p value '{raw}' → 기대 '{expected}', 실제 '{_val(r)}'"
    assert r.claims[0].unit == "%p", f"unit 보존 실패: {r.claims[0].unit!r}"


# -- 배수 --
@pytest.mark.asyncio
@pytest.mark.parametrize("raw,expected", [
    ("2배",   "2.0"),
    ("3배",   "3.0"),
    ("절반",  "0.5"),
    ("반",    "0.5"),
    ("갑절",  "2.0"),
])
async def test_multiplier(raw, expected):
    r = _make(raw)
    await normalize_claim(r)
    assert _val(r) == expected, f"배수 '{raw}' → 기대 '{expected}', 실제 '{_val(r)}'"


# -- 비교 기준(period 정규화) --
@pytest.mark.asyncio
@pytest.mark.parametrize("period_raw,expected_period", [
    ("2024년",     "2024"),
    ("2023년 1월", "2023-01"),
    ("전년",       "2023"),     # base 2024-01 기준
    ("전월",       "2023-12"),  # 2024-01 의 전월 (연도 롤오버)
    ("전분기",     "2023-Q4"),  # 2024-Q1 의 전분기
])
async def test_period_normalization(period_raw, expected_period):
    r = _make("100", period_raw)
    await normalize_claim(r)
    assert _period(r) == expected_period, (
        f"시점 '{period_raw}' → 기대 '{expected_period}', 실제 '{_period(r)}'"
    )


# ================================================================== #
# ⑥ 비율·분수
# ================================================================== #

@pytest.mark.asyncio
@pytest.mark.parametrize("raw,expected", [
    # 퍼센트
    ("32%",       "0.32"),
    ("32퍼센트",  "0.32"),
    ("100%",      "1.0"),
    ("0.5%",      "0.005"),
    # 분수
    ("5분의 1",   "0.2"),
    ("2분의 1",   "0.5"),
    ("3분의 2",   "0.6667"),  # 반올림 4자리
    ("4분의 3",   "0.75"),
    # 어림 비율
    ("절반",      "0.5"),
    ("반",        "0.5"),
    ("과반",      "0.5"),    # 0.5 초과이나 하한값으로 처리
    # 비(比)
    ("2 대 1",    "2:1"),
    ("3 대 2",    "3:2"),
    # 할·푼·리
    ("3할",       "0.3"),
    ("3할 2푼",   "0.32"),
    ("3할 2푼 5리","0.325"),
    ("타율 3할",  "0.3"),
])
async def test_ratio_fraction(raw, expected):
    r = _make(raw, unit="%")
    await normalize_claim(r)
    assert _val(r) == expected, f"비율 '{raw}' → 기대 '{expected}', 실제 '{_val(r)}'"
