"""KOSIS 응답 list[dict] → 한 셀 매칭.

매칭은 (PRD_DE, match_filters) 으로. 코드값 정확 일치 (== 비교) — substring
함정 회피 (메모리 kosis-api-response-shape).
"""
from __future__ import annotations

from src.kosis.types import KosisCell


def find_cell_row(
    rows: list[dict], period: str, match_filters: dict[str, str]
) -> dict | None:
    """매칭 row 한 개 반환. 없으면 None.

    조건: PRD_DE == period AND 모든 match_filters[k] == row[k].
    """
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("PRD_DE") != period:
            continue
        if all(row.get(k) == v for k, v in match_filters.items()):
            return row
    return None


def to_cell(row: dict) -> KosisCell:
    """row dict → KosisCell. DT 는 float 으로 변환 (KOSIS 가 문자열로 줌)."""
    dt_raw = row.get("DT", "")
    try:
        value = float(dt_raw)
    except (TypeError, ValueError) as e:
        raise ValueError(f"DT 값 float 변환 실패: {dt_raw!r}") from e
    return KosisCell(
        period=row.get("PRD_DE", ""),
        value=value,
        value_raw=str(dt_raw),
        unit=row.get("UNIT_NM", ""),
        lst_chn_de=row.get("LST_CHN_DE"),
        raw=row,
    )
