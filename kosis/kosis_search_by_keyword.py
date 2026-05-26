"""
KOSIS 통합검색 - 키워드로 가장 적합한 통계표 찾기
===================================================

KOSIS 공유서비스(OpenAPI)의 "KOSIS통합검색" 서비스(statisticsSearch.do)를
이용하여, 키워드에 가장 적합한 통계표 상위 N개를 조회한다.
각 검색의 소요시간(초)을 함께 측정/출력한다.

엔드포인트:
    https://kosis.kr/openapi/statisticsSearch.do?method=getList

요청변수:
    searchNm     : 검색어 (필수)
    startCount   : 시작 위치(페이지). 1이면 1번부터
    resultCount  : 결과 개수
    sort         : RANK(정확도순, 기본) | DATE(최신순)

API 키는 .env 파일의 KOSIS_API_KEY 에서 읽는다.
"""

from __future__ import annotations

import os
import time
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

import requests
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("kosis_search")

SEARCH_URL = "https://kosis.kr/openapi/statisticsSearch.do"


class KosisAPIError(RuntimeError):
    """KOSIS API가 에러 응답을 반환했을 때 발생."""


@dataclass
class SearchHit:
    """검색 결과 통계표 한 건 (핵심 필드만 추림)."""

    org_id: str
    tbl_id: str
    tbl_nm: str
    org_nm: str = ""
    stat_nm: str = ""      # 통계(조사)명
    prd_de: str = ""       # 수록 시점/기간 정보
    full: dict[str, Any] = None  # 원본 응답(필요 시 참조)

    @classmethod
    def from_raw(cls, d: dict[str, Any]) -> "SearchHit":
        return cls(
            org_id=str(d.get("ORG_ID", "")),
            tbl_id=str(d.get("TBL_ID", "")),
            tbl_nm=str(d.get("TBL_NM", "")),
            org_nm=str(d.get("ORG_NM", "")),
            stat_nm=str(d.get("STAT_NM", "")),
            prd_de=str(d.get("PRD_DE", d.get("FULL_PATH_ID", ""))),
            full=d,
        )


class KosisSearch:
    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        timeout: int = 30,
        retries: int = 3,
    ) -> None:
        if api_key is None:
            load_dotenv()
            api_key = os.getenv("KOSIS_API_KEY")
        if not api_key:
            raise ValueError(
                "API 키가 없습니다. .env 파일에 KOSIS_API_KEY=... 를 지정하세요."
            )
        self.api_key = api_key
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()

    # ------------------------------------------------------------------ #
    def _request(self, params: dict[str, str]) -> Any:
        params = {
            "method": "getList",
            "apiKey": self.api_key,
            "format": "json",
            "jsonVD": "Y",
            **params,
        }
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(
                    SEARCH_URL, params=params, timeout=self.timeout
                )
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, json.JSONDecodeError) as exc:
                last_exc = exc
                wait = 0.5 * attempt
                logger.warning(
                    "요청 실패 (%d/%d): %s — %.1fs 후 재시도",
                    attempt, self.retries, exc, wait,
                )
                time.sleep(wait)
                continue
            if isinstance(data, dict) and ("err" in data or "errMsg" in data):
                raise KosisAPIError(
                    f"{data.get('err', '?')}: {data.get('errMsg', data)}"
                )
            if isinstance(data, dict):
                return [data]
            return data or []
        raise KosisAPIError(f"최대 재시도 초과: {last_exc}")

    # ------------------------------------------------------------------ #
    def search(
        self,
        keyword: str,
        *,
        top_n: int = 5,
        sort: str = "RANK",
    ) -> tuple[list[SearchHit], float]:
        """
        키워드로 상위 top_n개 통계표를 조회한다.
        반환: (결과 리스트, 소요시간_초)
        """
        t0 = time.perf_counter()
        raw = self._request(
            {
                "searchNm": keyword,
                "startCount": "1",
                "resultCount": str(top_n),
                "sort": sort,
            }
        )
        elapsed = time.perf_counter() - t0

        hits = [SearchHit.from_raw(d) for d in raw][:top_n]
        logger.info(
            "검색 '%s': %d건 (%.3f초)", keyword, len(hits), elapsed
        )
        return hits, elapsed

    def search_many(
        self,
        keywords: list[str],
        *,
        top_n: int = 5,
        sort: str = "RANK",
    ) -> dict[str, list[SearchHit]]:
        """여러 키워드를 순회 검색. 키워드별 소요시간과 총합을 출력."""
        results: dict[str, list[SearchHit]] = {}
        total = 0.0
        for kw in keywords:
            hits, elapsed = self.search(kw, top_n=top_n, sort=sort)
            results[kw] = hits
            total += elapsed
        logger.info(
            "전체 %d개 키워드, 총 %.3f초 (평균 %.3f초/키워드)",
            len(keywords), total, total / len(keywords) if keywords else 0,
        )
        return results

    # ------------------------------------------------------------------ #
    @staticmethod
    def print_hits(keyword: str, hits: list[SearchHit]) -> None:
        print(f"\n=== '{keyword}' 상위 {len(hits)}개 ===")
        for i, h in enumerate(hits, 1):
            print(f"{i}. {h.tbl_nm}")
            print(f"   orgId={h.org_id}  tblId={h.tbl_id}  기관={h.org_nm}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="KOSIS 통합검색으로 키워드별 적합 통계표 상위 N개 조회"
    )
    parser.add_argument("keywords", nargs="+", help="검색 키워드 (여러 개 가능)")
    parser.add_argument("--top", type=int, default=5, help="키워드당 결과 개수")
    parser.add_argument(
        "--sort", default="RANK", choices=["RANK", "DATE"],
        help="정렬: RANK(정확도) | DATE(최신순)",
    )
    args = parser.parse_args()

    s = KosisSearch()
    results = s.search_many(args.keywords, top_n=args.top, sort=args.sort)
    for kw, hits in results.items():
        s.print_hits(kw, hits)


if __name__ == "__main__":
    main()
