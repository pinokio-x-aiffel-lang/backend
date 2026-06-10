"""DART 파서 단위 테스트 (네트워크/API 키 불필요).

parse_won, parse_income_statement_amount 의 순수 로직만 검증한다.
fixture 는 '로쏘' 감사보고서(rcept_no=20240408002669) 손익계산서 표의 축약본.

대상 모듈: src.dart.financials, src.dart.accounts
작성자: leeaain2027 <leeaain2027@gmail.com>
작성일: 2026-06-02
"""
from __future__ import annotations

from src.dart.accounts import resolve_account
from src.dart.financials import (
    detect_unit_multiplier,
    find_account_row,
    parse_income_statement_amount,
    parse_won,
)


def test_parse_won_basic():
    assert parse_won("124,315,432,968") == 124_315_432_968.0
    assert parse_won("(53,665,438)") == -53_665_438.0
    assert parse_won("-") is None
    assert parse_won("") is None
    assert parse_won("abc") is None


# 로쏘 손익계산서 축약 (제23(당)기 / 제22(전)기)
_AUDIT_FIXTURE = """
<TABLE><TR><TD>과 목</TD><TD>제 23(당) 기</TD><TD>제 22(전) 기</TD></TR>
<TR><TD>Ⅰ.매출액</TD><TD>124,315,432,968</TD><TD>81,736,550,003</TD></TR>
<TR><TD>1.제품매출</TD><TD>123,619,029,890</TD><TD>81,053,477,067</TD></TR>
<TR><TD>Ⅱ.매출원가</TD><TD>65,825,236,018</TD><TD>46,261,681,600</TD></TR>
</TABLE>
""".encode("utf-8")


def test_parse_income_statement_amount_picks_current_period():
    raw, period = parse_income_statement_amount(_AUDIT_FIXTURE, "매출액")
    assert raw == "124,315,432,968"          # 당기(왼쪽 열), 전기 아님
    assert parse_won(raw) == 124_315_432_968.0
    assert period == "제 23(당) 기"


def test_parse_income_statement_amount_no_match():
    raw, period = parse_income_statement_amount(_AUDIT_FIXTURE, "영업이익")
    assert raw is None and period is None


# --- 계정 별칭 / account_id 매칭 ------------------------------------------

def test_resolve_account_groups_revenue_labels():
    # 라벨이 달라도 같은 그룹으로
    ids, names = resolve_account("매출")
    assert "ifrs-full_Revenue" in ids
    assert {"매출액", "영업수익"} <= names
    assert resolve_account("영업수익") == resolve_account("매출액")
    # 모르는 계정은 자기 자신만 (후방호환)
    assert resolve_account("희한한계정") == (frozenset(), frozenset({"희한한계정"}))


def test_find_account_row_matches_by_account_id_despite_label():
    # 삼성전자 케이스: 라벨은 '영업수익'이지만 표준 id 로 '매출' 질의에 매칭
    rows = [
        {"account_id": "ifrs-full_Revenue", "account_nm": "영업수익",
         "sj_div": "IS", "thstrm_amount": "258935494000000"},
        {"account_id": "ifrs-full_GrossProfit", "account_nm": "매출총이익",
         "sj_div": "IS", "thstrm_amount": "78546914000000"},
    ]
    row = find_account_row(rows, "매출", sj_div="IS")
    assert row is not None and row["account_nm"] == "영업수익"


def test_parse_income_statement_amount_via_alias():
    # 원문 라벨이 '영업수익'이어도 '매출' 질의로 당기 금액을 잡는다
    doc = (
        "<TR><TD>과 목</TD><TD>제 10(당) 기</TD><TD>제 9(전) 기</TD></TR>"
        "<TR><TD>Ⅰ.영업수익</TD><TD>9,670,643,576,585</TD><TD>8,000,000,000,000</TD></TR>"
    ).encode("utf-8")
    raw, period = parse_income_statement_amount(doc, "매출")
    assert raw == "9,670,643,576,585"
    assert period == "제 10(당) 기"


# 쿠팡 케이스: 주석(註) 열 "21,26" 을 건너뛰고 당기 금액을 잡아야 한다
_NOTE_COLUMN_FIXTURE = (
    "<TR><TD>과 목</TD><TD>주석</TD><TD>제 11(당)기</TD><TD>제 10(전)기</TD></TR>"
    "<TR><TD>Ⅰ. 매출액</TD><TD>21,26</TD><TD>31,422,148</TD><TD>26,356,028</TD></TR>"
).encode("utf-8")


def test_parse_skips_note_column():
    raw, period = parse_income_statement_amount(_NOTE_COLUMN_FIXTURE, "매출")
    assert raw == "31,422,148"          # 주석 "21,26" 아님
    assert period == "제 11(당)기"


def test_detect_unit_multiplier():
    assert detect_unit_multiplier("(단위: 백만원)".encode("utf-8")) == 1_000_000
    assert detect_unit_multiplier("단위: 천원".encode("utf-8")) == 1_000
    assert detect_unit_multiplier("단위 : 원".encode("utf-8")) == 1
    assert detect_unit_multiplier("단위 표기 없음".encode("utf-8")) == 1


def test_resolve_account_balance_sheet_and_cashflow():
    ids, _ = resolve_account("자산총계")
    assert "ifrs-full_Assets" in ids
    ids, _ = resolve_account("영업활동현금흐름")
    assert "ifrs-full_CashFlowsFromUsedInOperatingActivities" in ids
    assert resolve_account("영업활동으로인한현금흐름") == resolve_account("영업활동현금흐름")


# 로쏘 실제 구조: <TE> 셀 + 전각공백(　) 주석칸
_TE_FIXTURE = (
    "<TR><TE>Ⅰ.매출액</TE><TE>　</TE>"
    "<TE>124,315,432,968</TE><TE>81,736,550,003</TE></TR>"
).encode("utf-8")


def test_parse_cell_te_skips_empty_note_cell():
    raw, _ = parse_income_statement_amount(_TE_FIXTURE, "매출")
    assert raw == "124,315,432,968"  # 빈 주석칸(　) 건너뛰고 당기


def test_detect_unit_multiplier_position_aware():
    # 로쏘 케이스: 본문=원, 주석=천원 혼재. 금액 직전은 '원' 이어야 한다.
    doc = (
        "(단위 : 원) Ⅰ.매출액 124,315,432,968 "
        "주석 (단위 : 천원) 구분 100 (단위 : 천원) 200"
    ).encode("utf-8")
    assert detect_unit_multiplier(doc, near="124,315,432,968") == 1
    assert detect_unit_multiplier(doc) == 1_000  # 전역 최빈은 천원(오답) → near 필요
