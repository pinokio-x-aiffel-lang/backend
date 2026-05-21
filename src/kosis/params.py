"""KosisQuery → KOSIS API params dict.

KOSIS statisticsParameterData.do (method=getList) 의 필수/선택 파라미터.
시점은 startPrdDe=endPrdDe=period 로 명시적. newEstPrdCnt 는 과거 검증
부적합 (메모리 kosis-api-response-shape).
"""
from __future__ import annotations

from src.kosis.types import KosisQuery


def build_params(query: KosisQuery, api_key: str) -> dict:
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
