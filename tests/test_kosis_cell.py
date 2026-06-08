"""KOSIS cell 모듈 라이브 테스트 — statisticsParameterData.do 단일 셀 조회.

src/kosis/cell.py 의 fetch_cell 로 실제 KOSIS 에서 **특정 한 셀**의 값을
조회해온다(좌표: orgId/tblId/itmId + objL 분류축 + 시점). itmId/objL 코드는
metadata(getMeta)에서 온다 — 여기서는 미리 확인한 코드를 상수로 고정한다.

네트워크 + KOSIS_API_KEY(.env) 필요. 키가 없으면 라이브 테스트는 skip.
오프라인 테스트(find_cell_row/to_cell)는 키 없이도 항상 실행된다.

주의: 검증용 표 DT_1B040A3 은 분류축이 1개(행정구역)뿐이라 obj_l2 는 빈
문자열("")이어야 한다. 기본값 obj_l2="ALL" 로는 err:21(잘못된 요청)로 실패한다.

실행:
    uv run pytest tests/test_kosis_cell.py -v
    uv run python tests/test_kosis_cell.py        # 스크립트로(상세 출력)

대상 모듈: src.kosis.cell (fetch_cell / find_cell_row / to_cell)
작성자: leeaain2027 <leeaain2027@gmail.com>
작성일: 2026-06-08
"""
from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from src.kosis.cell import KosisCell, KosisQuery, fetch_cell, find_cell_row, to_cell

load_dotenv()

# 검증용 셀: 통계청 「주민등록인구현황」 행정구역별 인구 (DT_1B040A3)
#   itmId=T20(총인구수), 행정구역 C1=00(전국), prdSe=Y(연간), 2023년
ORG_ID = "101"
TBL_ID = "DT_1B040A3"
ITM_ID = "T20"          # 총인구수
REGION_NATION = "00"    # 전국 (행정구역 분류축 = objL1, 응답 컬럼 C1)
PERIOD = "2023"
PERIOD_SE = "Y"

# 이 시점(2023) 전국 총인구수의 알려진 값. KOSIS 재집계 시 갱신 필요할 수 있어
# 정확값 대신 합리적 범위(5천만~5천2백만)로 검증한다.
EXPECTED_MIN = 50_000_000
EXPECTED_MAX = 52_000_000


def _nation_query(period: str = PERIOD) -> KosisQuery:
    """전국 총인구수 한 셀을 가리키는 KosisQuery (obj_l2=\"\" 필수)."""
    return KosisQuery(
        org_id=ORG_ID,
        tbl_id=TBL_ID,
        itm_id=ITM_ID,
        period=period,
        period_se=PERIOD_SE,
        obj_l1=REGION_NATION,
        obj_l2="",                       # 분류축 1개뿐 → "ALL" 아닌 빈 값
        match_filters={"C1": REGION_NATION},
    )


live = pytest.mark.skipif(
    not os.getenv("KOSIS_API_KEY"),
    reason="KOSIS_API_KEY 가 .env 에 없어 live 셀 조회 테스트를 건너뜀",
)


# ---- 라이브: 실제 KOSIS 에서 특정 셀 값이 조회되는지 ------------------------

@live
def test_fetch_specific_cell():
    """전국 총인구수(2023) 한 셀 → KosisCell, 값이 합리적 범위 내."""
    cell = fetch_cell(_nation_query(), os.environ["KOSIS_API_KEY"])

    assert cell is not None, "셀이 조회되지 않음 (None)"
    assert isinstance(cell, KosisCell)
    assert cell.period == PERIOD
    assert isinstance(cell.value, float)
    assert EXPECTED_MIN < cell.value < EXPECTED_MAX, (
        f"전국 인구수 값이 예상 범위를 벗어남: {cell.value}"
    )
    assert cell.value_raw  # 원문 문자열 존재
    assert cell.unit       # 단위(명) 존재


@live
def test_fetch_cell_no_match_returns_none():
    """행은 받았지만 match_filters 가 어떤 행과도 안 맞으면 None (예외 아님).

    유효한 시점(2023)·전국 조회라 KOSIS 는 행을 돌려주지만, 존재하지 않는
    분류 코드(C1=99)로 거르면 find_cell_row 가 None → fetch_cell None.
    (존재하지 않는 시점은 KOSIS 가 err:30 으로 막아 None 경로가 아님.)
    """
    q = KosisQuery(
        org_id=ORG_ID, tbl_id=TBL_ID, itm_id=ITM_ID,
        period=PERIOD, period_se=PERIOD_SE,
        obj_l1=REGION_NATION, obj_l2="",
        match_filters={"C1": "99"},   # 응답엔 C1=00 만 → 매칭 0건
    )
    assert fetch_cell(q, os.environ["KOSIS_API_KEY"]) is None


# ---- 오프라인: 셀 선택/정규화 로직 (네트워크 불필요, 항상 실행) ------------

_FAKE_ROWS = [
    {"PRD_DE": "2023", "C1": "00", "DT": "51325329", "UNIT_NM": "명",
     "LST_CHN_DE": "2024-02-28"},
    {"PRD_DE": "2023", "C1": "11", "DT": "9386034", "UNIT_NM": "명"},   # 서울
    {"PRD_DE": "2022", "C1": "00", "DT": "51439038", "UNIT_NM": "명"},
]


def test_find_cell_row_matches_by_code():
    """PRD_DE + match_filters(코드값 ==)로 정확히 한 행을 고른다."""
    row = find_cell_row(_FAKE_ROWS, "2023", {"C1": "00"})
    assert row is not None and row["DT"] == "51325329"


def test_find_cell_row_no_match_returns_none():
    """조건에 맞는 행이 없으면 None."""
    assert find_cell_row(_FAKE_ROWS, "2023", {"C1": "99"}) is None
    assert find_cell_row(_FAKE_ROWS, "1999", {"C1": "00"}) is None


def test_to_cell_parses_dt_to_float():
    """to_cell: DT 문자열 → float, 부가 필드 매핑."""
    cell = to_cell(_FAKE_ROWS[0])
    assert cell.value == 51325329.0
    assert cell.value_raw == "51325329"
    assert cell.unit == "명"
    assert cell.period == "2023"
    assert cell.lst_chn_de == "2024-02-28"


def test_to_cell_raises_on_non_numeric_dt():
    """DT 가 숫자가 아니면 ValueError."""
    with pytest.raises(ValueError):
        to_cell({"PRD_DE": "2023", "DT": "-", "UNIT_NM": "명"})


if __name__ == "__main__":
    # 스크립트 실행: 실제 셀 값을 사람이 보기 좋게 출력
    if not os.getenv("KOSIS_API_KEY"):
        raise SystemExit("KOSIS_API_KEY 가 .env 에 없습니다.")
    cell = fetch_cell(_nation_query(), os.environ["KOSIS_API_KEY"])
    if cell is None:
        print("조회 결과: 매칭 셀 없음 (None)")
    else:
        print(f"표 {ORG_ID}/{TBL_ID} itmId={ITM_ID} C1={REGION_NATION} {PERIOD}")
        print(f"  → {cell.value:,.0f} {cell.unit} (원문 {cell.value_raw!r}, "
              f"최종변경 {cell.lst_chn_de})")
