"""KOSIS 통계자료(statisticsParameterData.do): 한 셀 조회. [파이프라인 5]

지정한 좌표(orgId/tblId/itmId + objL 분류축 + 시점)의 통계 데이터를 받아
PRD_DE·분류 코드로 한 셀을 골라 정규화한다. itmId/objL 코드의 출처는 metadata.py.

흐름: KosisQuery → params(build_params) → 공유 client.call_kosis
      → 한 행 매칭(find_cell_row) → 정규화(to_cell, KosisCell).
코드값(C1/C2...)을 `_NM`(이름)이 아닌 코드로 정확 일치(== 비교) 매칭해
substring 함정을 피한다(메모리 kosis-api-response-shape).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.kosis.client import call_kosis


@dataclass(frozen=True)
class KosisQuery:
    """KOSIS 셀 조회 입력. (orgId, tblId, period, classification) + obj 축.

    `match_filters` 는 응답 row 에서 한 셀을 골라낼 키-값 쌍.
    예: {"C1": "10", "C2": "00"} → C1 코드 "10" 이고 C2 코드 "00" 인 셀.
    `_NM` 필드 (이름) 가 아닌 코드값으로 매칭해야 substring 함정 회피
    (참고: 메모리 kosis-api-response-shape).
    """

    org_id: str
    tbl_id: str
    itm_id: str
    period: str
    period_se: str
    match_filters: dict[str, str] = field(default_factory=dict)
    obj_l1: str = "ALL"
    obj_l2: str = "ALL"


@dataclass(frozen=True)
class KosisCell:
    """KOSIS 한 셀의 정규화된 표현 (Evidence 모듈 입력)."""

    period: str
    value: float
    value_raw: str
    unit: str
    lst_chn_de: str | None
    raw: dict


def build_params(query: KosisQuery, api_key: str) -> dict:
    """KosisQuery → statisticsParameterData.do(method=getList) params dict.

    시점은 startPrdDe=endPrdDe=period 로 명시적. newEstPrdCnt 는 과거 검증
    부적합 (메모리 kosis-api-response-shape).
    """
    return {
        "method": "getList",
        "apiKey": api_key,
        "itmId": query.itm_id,
        "objL1": query.obj_l1,
        "objL2": query.obj_l2,
        "objL3": "", "objL4": "", "objL5": "",
        "objL6": "", "objL7": "", "objL8": "",
        "format": "json",
        "jsonVD": "Y",
        "prdSe": query.period_se,
        "startPrdDe": query.period,
        "endPrdDe": query.period,
        "orgId": query.org_id,
        "tblId": query.tbl_id,
    }


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
