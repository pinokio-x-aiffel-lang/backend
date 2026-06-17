"""KOSIS 통합검색(statisticsSearch.do): 키워드 → 통계표 후보. [파이프라인 4]

키워드에 적합한 통계표 상위 N개를 찾는다. 공유 HTTP 레이어(client.kosis_get)를
거쳐 Session·재시도·rate limit·jsonVD=Y 가 적용된다.

응답 필드는 statisticsSearch.do 고정 스키마(ORG_ID/TBL_ID/TBL_NM/STRT_PRD_DE/
END_PRD_DE/...). 이 엔드포인트엔 PRD_DE 가 없고 수록 기간은 STRT_PRD_DE~END_PRD_DE.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from src.kosis.client import SEARCH_URL, KosisError, kosis_get, resolve_api_key

logger = logging.getLogger("kosis")

_VALID_SORTS = ("RANK", "DATE")


@dataclass(frozen=True)
class SearchHit:
    """검색 결과 통계표 한 건 (핵심 필드만 추림)."""

    org_id: str
    tbl_id: str
    tbl_nm: str
    org_nm: str = ""
    stat_nm: str = ""           # 통계(조사)명
    prd_de: str = ""            # 수록 기간 (STRT_PRD_DE~END_PRD_DE)
    raw: Optional[dict[str, Any]] = None  # 원본 응답(필요 시 참조)

    @classmethod
    def from_raw(cls, d: dict[str, Any]) -> "SearchHit":
        # 통합검색 응답엔 PRD_DE 가 없어 수록 기간을 STRT~END 로 합친다.
        # 둘 다 비면 분류 경로 식별자(FULL_PATH_ID)로 방어적으로 대체.
        strt = str(d.get("STRT_PRD_DE", "")).strip()
        end = str(d.get("END_PRD_DE", "")).strip()
        prd_de = f"{strt}~{end}".strip("~") or str(d.get("FULL_PATH_ID", ""))
        return cls(
            org_id=str(d.get("ORG_ID", "")),
            tbl_id=str(d.get("TBL_ID", "")),
            tbl_nm=str(d.get("TBL_NM", "")),
            org_nm=str(d.get("ORG_NM", "")),
            stat_nm=str(d.get("STAT_NM", "")),
            prd_de=prd_de,
            raw=d,
        )


def search_tables(
    keyword: str,
    api_key: Optional[str] = None,
    *,
    top_n: int = 5,
    sort: str = "RANK",
) -> list[SearchHit]:
    """키워드로 상위 top_n개 통계표를 조회한다. 빈 키워드 → [].

    Raises:
        ValueError: sort 가 RANK/DATE 가 아니거나 API 키가 없는 경우.
        KosisError: KOSIS 호출 실패.
    """
    if not keyword or not keyword.strip():
        return []
    if sort not in _VALID_SORTS:
        raise ValueError(f"sort 는 {_VALID_SORTS} 중 하나여야 합니다: {sort!r}")

    t0 = time.perf_counter()
    rows = kosis_get(
        SEARCH_URL,
        {
            "method": "getList",
            "apiKey": resolve_api_key(api_key),
            "searchNm": keyword.strip(),
            "startCount": "1",
            "resultCount": str(min(top_n, 1000)),  # resultCount 상한 1000
            "sort": sort,
        },
    )
    hits = [SearchHit.from_raw(d) for d in rows][:top_n]
    logger.info(
        "KOSIS 검색 '%s': %d건 (%.3fs)",
        keyword.strip(), len(hits), time.perf_counter() - t0,
    )
    return hits


def search_tables_many(
    keywords: list[str],
    api_key: Optional[str] = None,
    *,
    top_n: int = 5,
    sort: str = "RANK",
) -> dict[str, list[SearchHit]]:
    """여러 키워드를 순회 검색. 키워드별 결과 dict + 총/평균 소요시간 로깅."""
    results: dict[str, list[SearchHit]] = {}
    t0 = time.perf_counter()
    for kw in keywords:
        try:
            results[kw] = search_tables(kw, api_key, top_n=top_n, sort=sort)
        except KosisError as exc:
            # 한 키워드 실패가 다른 변형 결과까지 버리지 않게 흡수([4] 다중검색용).
            logger.warning("KOSIS 검색 '%s' 실패(흡수): %s", kw, exc)
            results[kw] = []
    total = time.perf_counter() - t0
    logger.info(
        "KOSIS 검색 %d개 키워드: 총 %.3fs (평균 %.3fs/키워드)",
        len(keywords), total, total / len(keywords) if keywords else 0.0,
    )
    return results
