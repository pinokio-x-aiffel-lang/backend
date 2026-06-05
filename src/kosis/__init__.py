"""KOSIS 호출 모듈.

Public API:
  search_tables(keyword, api_key) -> list[SearchHit]  통계표 후보 검색 [단계 4]
  fetch_cell(query, api_key) -> KosisCell | None       한 셀 조회 [단계 5]
  SearchHit / KosisQuery / KosisCell                   입력/출력 타입
  KosisError                                           호출 실패 예외

내부 (debug/테스트용):
  kosis_get, call_kosis, find_cell_row, to_cell, build_params,
  convert_to_claim_unit, find_unit_group, UNIT_GROUPS
"""
from src.kosis.client import KosisError, call_kosis, kosis_get
from src.kosis.matcher import find_cell_row, to_cell
from src.kosis.params import build_params
from src.kosis.search import SearchHit, search_tables, search_tables_many
from src.kosis.types import KosisCell, KosisQuery
from src.kosis.units import (
    UNIT_GROUPS,
    convert_to_claim_unit,
    find_unit_group,
)


def fetch_cell(query: KosisQuery, api_key: str) -> KosisCell | None:
    """KOSIS 한 셀 조회. None = 매칭 0건.

    Raises:
        KosisError: API 호출 실패 또는 응답 비정상.
        ValueError: 매칭된 row 의 DT 가 float 변환 안 됨.
    """
    params = build_params(query, api_key)
    rows = call_kosis(params)
    row = find_cell_row(rows, query.period, query.match_filters)
    return to_cell(row) if row else None


__all__ = [
    "KosisQuery",
    "KosisCell",
    "SearchHit",
    "KosisError",
    "search_tables",
    "search_tables_many",
    "fetch_cell",
    "kosis_get",
    "call_kosis",
    "find_cell_row",
    "to_cell",
    "build_params",
    "convert_to_claim_unit",
    "find_unit_group",
    "UNIT_GROUPS",
]
