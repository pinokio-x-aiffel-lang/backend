"""KOSIS 모듈 데이터 타입.

KosisQuery: 한 셀을 식별하는 입력. 아인님의 retrieval funnel 결과.
KosisCell:  KOSIS 한 셀의 정규화된 표현 (Evidence 모듈 입력).
"""
from __future__ import annotations

from dataclasses import dataclass, field


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
    """KOSIS 한 셀의 정규화된 표현."""
    period: str
    value: float
    value_raw: str
    unit: str
    lst_chn_de: str | None
    raw: dict
