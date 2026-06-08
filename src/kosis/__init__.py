"""KOSIS 호출 모듈.

Public API:
  search_tables(keyword, api_key) -> list[SearchHit]  통계표 후보 검색 [단계 4]
  fetch_table_meta(orgId, tblId) -> TableMeta          통계표 구조 메타(getMeta)
  resolve_cell_query(orgId, tblId, ...) -> KosisQuery  좌표 해소(이름매칭) [단계 5 전반]
  fetch_cell(query, api_key) -> KosisCell | None       한 셀 조회 [단계 5]
  SearchHit / TableMeta / KosisQuery / KosisCell       입력/출력 타입
  KosisError / ResolveError                            호출/해소 실패 예외

내부 (debug/테스트용):
  kosis_get, call_kosis, resolve_api_key, find_cell_row, to_cell, build_params,
  fetch_meta_item, META_ITEMS, convert_to_claim_unit, find_unit_group, UNIT_GROUPS
"""
from src.kosis.cell import (
    KosisCell,
    KosisQuery,
    build_params,
    fetch_cell,
    fetch_cell_with_retry,
    find_cell_row,
    to_cell,
)
from src.kosis.client import KosisError, call_kosis, kosis_get, resolve_api_key
from src.kosis.metadata import META_ITEMS, TableMeta, fetch_meta_item, fetch_table_meta
from src.kosis.resolve import (
    ResolveError,
    resolve_cell_query,
    resolve_cell_query_traced,
)
from src.kosis.search import SearchHit, search_tables, search_tables_many
from src.kosis.units import (
    UNIT_GROUPS,
    convert_to_claim_unit,
    find_unit_group,
)


__all__ = [
    "KosisQuery",
    "KosisCell",
    "SearchHit",
    "TableMeta",
    "KosisError",
    "search_tables",
    "search_tables_many",
    "fetch_table_meta",
    "fetch_meta_item",
    "META_ITEMS",
    "resolve_cell_query",
    "resolve_cell_query_traced",
    "ResolveError",
    "fetch_cell",
    "fetch_cell_with_retry",
    "kosis_get",
    "call_kosis",
    "resolve_api_key",
    "find_cell_row",
    "to_cell",
    "build_params",
    "convert_to_claim_unit",
    "find_unit_group",
    "UNIT_GROUPS",
]
