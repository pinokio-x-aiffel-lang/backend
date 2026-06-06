"""KOSIS 통계표 구조 메타데이터(statisticsData.do?method=getMeta).

통계표(orgId+tblId)의 항목(ITM)·분류축(OBJ)·시점(PRD)·단위 등 구조 메타를
type별로 조회한다. 셀 조회(cell.fetch_cell)에 필요한 itmId/objL/prdSe **코드의 출처**.
(긴 조사 설명문을 주는 statisticsExplData.do(통계설명)와는 다른 서비스.)

공유 HTTP 레이어(client.kosis_get)를 거쳐 Session·재시도·rate limit·jsonVD=Y 가
적용된다. getMeta 는 type 1개당 1종만 반환(type=ALL 없음)하므로 필요한 type 만
순회 조회한다. type별 실패(KosisError)는 TableMeta.errors 에 모아 두고 계속한다.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from src.kosis.client import META_URL, KosisError, kosis_get, resolve_api_key

logger = logging.getLogger("kosis")

# getMeta type 코드 → 한글 라벨. WGT(가중치) 포함 8종.
META_ITEMS: dict[str, str] = {
    "TBL": "통계표명칭",
    "ORG": "기관명칭",
    "PRD": "수록정보",
    "ITM": "분류항목",
    "CMMT": "주석",
    "UNIT": "단위",
    "SOURCE": "출처",
    "WGT": "가중치",
}


@dataclass
class TableMeta:
    """단일 통계표의 구조 메타데이터 묶음.

    items  : type → getMeta 응답(list/dict). 성공한 type 만 담긴다.
    errors : type → 에러 메시지. KOSIS 가 빈/오류 응답을 준 type.
    """

    org_id: str
    tbl_id: str
    items: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "orgId": self.org_id,
            "tblId": self.tbl_id,
            "items": self.items,
            "errors": self.errors,
        }


def fetch_meta_item(
    org_id: str,
    tbl_id: str,
    meta_type: str,
    api_key: Optional[str] = None,
) -> Any:
    """getMeta type 하나를 조회한다 (예: ITM, PRD, UNIT...).

    Raises:
        KosisError: KOSIS 가 빈/오류 응답(err/errMsg)을 준 경우.
        ValueError: API 키가 없는 경우.
    """
    return kosis_get(
        META_URL,
        {
            "method": "getMeta",
            "apiKey": resolve_api_key(api_key),
            "type": meta_type,
            "orgId": org_id,
            "tblId": tbl_id,
        },
    )


def fetch_table_meta(
    org_id: str,
    tbl_id: str,
    api_key: Optional[str] = None,
    *,
    meta_types: Optional[list[str]] = None,
) -> TableMeta:
    """통계표 1건의 메타를 type별로 수집한다. type별 실패는 errors 에 기록하고 계속.

    meta_types=None 이면 META_ITEMS 전체(8종)를 순회한다.

    Raises:
        ValueError: API 키가 없는 경우(키는 1회만 검증).
    """
    key = resolve_api_key(api_key)  # 키를 미리 한 번 검증/확보
    types = meta_types or list(META_ITEMS)
    result = TableMeta(org_id=org_id, tbl_id=tbl_id)

    t0 = time.perf_counter()
    for meta_type in types:
        try:
            result.items[meta_type] = fetch_meta_item(org_id, tbl_id, meta_type, key)
        except KosisError as exc:
            result.errors[meta_type] = str(exc)
    logger.info(
        "KOSIS 메타 orgId=%s tblId=%s: %d/%d type 성공 (%.3fs)",
        org_id, tbl_id, len(result.items), len(types), time.perf_counter() - t0,
    )
    return result
