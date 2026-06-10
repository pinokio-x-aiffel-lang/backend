"""KOSIS 호출 모듈.

Public API:
  search_tables(keyword, api_key) -> list[SearchHit]      통계표 후보 검색 [단계 4]
  fetch_table_metadata(orgId, tblId) -> TableMetadata     통계표 메타(ITM+PRD) [단계 5]
  map_claim_to_cell_query(orgId, tblId, ...) -> KosisQuery claim→셀 좌표 매핑 [단계 5]
  fetch_cell(query, api_key) -> KosisCell | None          한 셀 조회 [단계 5]
  SearchHit / TableMetadata / KosisQuery / KosisCell      입력/출력 타입
  KosisError / ClaimMappingError                          호출/매핑 실패 예외

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
from src.kosis.metadata import (
    META_ITEMS,
    Axis,
    Item,
    Period,
    TableMeta,
    TableMetadata,
    fetch_meta_item,
    fetch_table_meta,
    fetch_table_metadata,
)
from src.kosis.map_claim_to_cell import (
    ClaimMappingError,
    map_claim_to_cell_query,
    map_claim_to_cell_query_traced,
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
    "TableMetadata",
    "Item",
    "Axis",
    "Period",
    "KosisError",
    "search_tables",
    "search_tables_many",
    "fetch_table_meta",
    "fetch_table_metadata",
    "fetch_meta_item",
    "META_ITEMS",
    "map_claim_to_cell_query",
    "map_claim_to_cell_query_traced",
    "ClaimMappingError",
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
