"""DART(OpenDART) 공시 수치 조회 모듈.

Public API:
  fetch_fact(query, api_key) -> DartFact | None     기업 공시에서 한 수치 조회
  DartQuery / DartFact                               입력/출력 타입
  DartError                                          호출 실패 예외

조회 전략 (KOSIS fetch_cell 과 평행):
  1) corp_name → corp_code 해석
  2) fnlttSinglAcntAll (상장사/주요 비상장사) — 구조화 당기 금액
  3) 위가 없으면(013) 감사보고서 원문 파싱 (비상장 외감 폴백)

내부 (debug/테스트용):
  resolve_corp_code, fetch_structured_fact, fetch_audit_report_fact,
  search_disclosures, parse_won, parse_income_statement_amount,
  call_dart, fetch_zip_xml
"""
from src.dart.accounts import resolve_account
from src.dart.client import DartError, call_dart, fetch_zip_xml
from src.dart.corp_code import resolve_corp_code
from src.dart.financials import (
    detect_unit_multiplier,
    fetch_audit_report_fact,
    fetch_structured_fact,
    find_account_row,
    parse_income_statement_amount,
    parse_won,
    search_disclosures,
)
from src.dart.types import DartFact, DartQuery


def fetch_fact(query: DartQuery, api_key: str) -> DartFact | None:
    """공시에서 한 수치 조회. None = 기업/수치 매칭 0건.

    Raises:
        DartError: API 호출 실패 또는 응답 비정상.
    """
    corp_code = resolve_corp_code(query.corp_name, api_key)
    if corp_code is None:
        return None
    fact = fetch_structured_fact(corp_code, query, api_key)
    if fact is not None:
        return fact
    return fetch_audit_report_fact(corp_code, query, api_key)


__all__ = [
    "DartQuery",
    "DartFact",
    "DartError",
    "fetch_fact",
    "resolve_corp_code",
    "resolve_account",
    "fetch_structured_fact",
    "fetch_audit_report_fact",
    "find_account_row",
    "search_disclosures",
    "parse_won",
    "parse_income_statement_amount",
    "detect_unit_multiplier",
    "call_dart",
    "fetch_zip_xml",
]
