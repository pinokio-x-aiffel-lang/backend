"""KOSIS 통계자료(statisticsParameterData.do): 한 셀 조회. [파이프라인 5]

지정한 좌표(orgId/tblId/itmId + objL 분류축 + 시점)의 통계 데이터를 받아
PRD_DE·분류 코드로 한 셀을 골라 정규화한다. itmId/objL 코드의 출처는 metadata.py.

흐름: KosisQuery → params(build_params) → 공유 client.call_kosis
      → 한 행 매칭(find_cell_row) → 정규화(to_cell, KosisCell).
코드값(C1/C2...)을 `_NM`(이름)이 아닌 코드로 정확 일치(== 비교) 매칭해
substring 함정을 피한다(메모리 kosis-api-response-shape).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from src.kosis.client import KosisError, call_kosis


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
    obj_l2: str = ""
    obj_l3: str = ""
    obj_l4: str = ""


@dataclass(frozen=True)
class KosisCell:
    """KOSIS 한 셀의 정규화된 표현 (Evidence 모듈 입력)."""

    period: str
    value: float
    value_raw: str
    unit: str
    lst_chn_de: str | None
    raw: dict


# KOSIS 공식 문서 기준 prdSe 코드. 내부 period_type → API 전송값.
# 반기: 공식 코드 'H' (실제 API는 값을 무시하지만 문서 준수)
_PRDSE_API: dict[str, str] = {"S": "H"}


def build_params(query: KosisQuery, api_key: str) -> dict:
    """KosisQuery → statisticsParameterData.do(method=getList) params dict.

    시점은 startPrdDe=endPrdDe=period 로 명시적. newEstPrdCnt 는 과거 검증
    부적합 (메모리 kosis-api-response-shape).
    빈 문자열 objL 파라미터는 전송하지 않는다 — 빈값을 보내면 다축 분류표에서
    error 21(잘못된 요청 변수)이 발생한다. (MCP 참고: objL1=ALL만 보내도 성공)
    """
    params: dict = {
        "method": "getList",
        "apiKey": api_key,
        "itmId": query.itm_id,
        "objL1": query.obj_l1,
        "objL": query.obj_l1,  # 구 API 호환성 — 일부 테이블(분기 등)에서 필수
        "format": "json",
        "jsonVD": "Y",
        "prdSe": _PRDSE_API.get(query.period_se, query.period_se),
        "startPrdDe": query.period,
        "endPrdDe": query.period,
        "orgId": query.org_id,
        "tblId": query.tbl_id,
    }
    # 빈 문자열이 아닌 경우만 포함 (빈값 전송 시 KOSIS error 21 유발)
    for key, val in (
        ("objL2", query.obj_l2),
        ("objL3", query.obj_l3),
        ("objL4", query.obj_l4),
    ):
        if val:
            params[key] = val
    return params


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


def _is_obj_error(msg: str) -> bool:
    """error 20(필수변수 누락) 또는 21(잘못된 요청 변수) — objL 관련 오류 여부."""
    return msg.startswith("20:") or msg.startswith("21:")


def fetch_cell_with_retry(query: KosisQuery, api_key: str) -> KosisCell | None:
    """KOSIS 한 셀 조회 with progressive objL retry.

    다축 분류표(error 20/21)에 대해 MCP _execute_with_obj_retry 전략을 적용한다:
      Stage 0 : 원래 query 그대로 시도
      Stage 1 : objL1="ALL"
      Stage 2 : objL1="ALL", objL2="ALL"
      Stage 3 : objL1~objL3="ALL"
      Stage 4 : objL1~objL4="ALL"
    각 단계에서 error 20/21 이 아닌 오류는 그대로 re-raise.
    모든 단계 실패 후에도 매칭 0건이면 None 반환.
    """
    try:
        return fetch_cell(query, api_key)
    except KosisError as e:
        if not _is_obj_error(str(e)):
            raise

    _ALL_SEQS = [
        ("ALL", query.obj_l2, query.obj_l3, query.obj_l4),
        ("ALL", "ALL",        query.obj_l3, query.obj_l4),
        ("ALL", "ALL",        "ALL",        query.obj_l4),
        ("ALL", "ALL",        "ALL",        "ALL"),
    ]
    for l1, l2, l3, l4 in _ALL_SEQS:
        retry = dataclasses.replace(query, obj_l1=l1, obj_l2=l2, obj_l3=l3, obj_l4=l4)
        try:
            params = build_params(retry, api_key)
            rows = call_kosis(params)
            row = find_cell_row(rows, query.period, query.match_filters)
            return to_cell(row) if row else None
        except KosisError as e:
            if not _is_obj_error(str(e)):
                raise

    return None
