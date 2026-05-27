"""
KOSIS 통계목록 순회 수집기 (Async 버전)
=========================================

원본 ``kosis/kosis_list_crolling.py`` 의 동기·직렬 구현을 async + 글로벌
rate limiter 기반으로 재작성한 버전이다. 외부 인터페이스(StatTable, 출력
CSV/JSON, 체크포인트 파일 형식)는 원본과 동일하게 유지하므로 결과 비교가
가능하다.

병목 분석
----------
원본은 1초당 1회 직렬 호출로 4~5만 호출 → 약 13시간.
KOSIS OpenAPI 제한은 분당 1,000건이므로 이론상 50분이 최단 시간.

이 모듈의 전략
----------------
1. ``httpx.AsyncClient`` 로 in-flight 동시 요청 다수 유지(파이프 채우기).
2. **글로벌 rate limiter** 가 분당 900건(=안전 마진 10%) 으로 천장 고정.
3. **BFS 계층 단위 동시 호출**: 같은 깊이의 부모 노드들을 한 번에 fire
   (``asyncio.gather``).
4. **vwCd 12개도 동시 실행**: 모든 vwCd 코루틴이 같은 limiter 공유.
5. **429 응답에 지수 백오프** 후 재시도.

API 키는 .env 의 ``KOSIS_API_KEY`` 에서 읽는다 (원본과 동일).

실행 예
--------
    python kosis/innnn/kosis_list_crolling_async.py \\
        --rate 900 --concurrency 30 --csv kosis/innnn/kosis_tables_async.csv \\
        --checkpoint kosis/innnn/kosis_list_async.checkpoint
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Optional

import httpx
from dotenv import load_dotenv


# --------------------------------------------------------------------------- #
# 설정
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("kosis_list_async")

LIST_URL = "https://kosis.kr/openapi/statisticsList.do"

VIEW_CODES: dict[str, str] = {
    "MT_ZTITLE": "국내통계 주제별",
    "MT_OTITLE": "국내통계 기관별",
    "MT_GTITLE01": "e-지방지표(주제별)",
    "MT_GTITLE02": "e-지방지표(지역별)",
    "MT_CHOSUN_TITLE": "광복이전통계(1908~1943)",
    "MT_HANKUK_TITLE": "대한민국통계연감",
    "MT_STOP_TITLE": "작성중지통계",
    "MT_RTITLE": "국제통계",
    "MT_BUKHAN": "북한통계",
    "MT_TM1_TITLE": "대상별통계",
    "MT_TM2_TITLE": "이슈별통계",
    "MT_ETITLE": "영문 KOSIS",
}

ROOT_PARENT_ID = ""


class KosisAPIError(RuntimeError):
    """KOSIS API가 에러 응답을 반환했을 때 발생."""


# --------------------------------------------------------------------------- #
# 데이터 클래스 (원본과 동일)
# --------------------------------------------------------------------------- #
@dataclass
class StatTable:
    vw_cd: str
    org_id: str
    tbl_id: str
    tbl_nm: str
    list_id: str = ""

    def key(self) -> tuple[str, str]:
        return (self.org_id, self.tbl_id)


# --------------------------------------------------------------------------- #
# 글로벌 rate limiter — 외부 패키지 없이 구현
# --------------------------------------------------------------------------- #
class AsyncRateLimiter:
    """엄격 주기 limiter. 호출은 평균 ``period/max_per_period`` 초 간격으로 fire 된다.

    여러 코루틴이 같은 인스턴스를 공유하면, 전체 합산 호출률이 상한 아래로
    유지된다. KOSIS 의 분당 1,000건 제한 같은 글로벌 quota 에 적합하다.

    구현은 "다음 허용 시각(next_time)" 을 lock 으로 갱신하는 방식.
    sleep 중에도 lock 을 잡고 있어 후속 코루틴들이 자연스럽게 큐잉된다.
    """

    def __init__(self, max_per_period: float, period: float = 60.0) -> None:
        if max_per_period <= 0:
            raise ValueError("max_per_period must be > 0")
        self.interval = period / max_per_period  # seconds between requests
        self._next_time = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._next_time - now
            if wait > 0:
                await asyncio.sleep(wait)
            # 누적 지연이 음수가 되지 않도록 max() 로 클램프
            self._next_time = max(now, self._next_time) + self.interval


# --------------------------------------------------------------------------- #
# 비동기 순회 수집기
# --------------------------------------------------------------------------- #
class KosisListAsyncCrawler:
    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        timeout: float = 30.0,
        retries: int = 3,
        max_per_minute: float = 900,
        concurrency: int = 30,
        checkpoint_path: Optional[str] = None,
    ) -> None:
        """
        Parameters
        ----------
        api_key : str | None
            KOSIS 인증키. None 이면 .env 의 KOSIS_API_KEY.
        timeout : float
            HTTP 요청 타임아웃(초).
        retries : int
            요청 실패/429 시 최대 재시도 횟수.
        max_per_minute : float
            글로벌 호출률 상한 (기본 900 = KOSIS 제한 1,000 의 안전 마진 10%).
        concurrency : int
            동시 in-flight 요청 수 상한. 소켓·메모리 안전 장치.
        checkpoint_path : str | None
            방문 완료 노드(vwCd, listId) 기록 파일.
        """
        if api_key is None:
            load_dotenv()
            api_key = os.getenv("KOSIS_API_KEY")
        if not api_key:
            raise ValueError(
                "API 키가 없습니다. .env 의 KOSIS_API_KEY 를 지정하세요."
            )

        self.api_key = api_key
        self.timeout = timeout
        self.retries = retries
        self.checkpoint_path = checkpoint_path

        self._limiter = AsyncRateLimiter(max_per_minute, period=60.0)
        self._sem = asyncio.Semaphore(concurrency)
        self._cp_lock = asyncio.Lock()

        # 방문 완료한 (vwCd, listId)
        self._visited: set[tuple[str, str]] = set()
        if checkpoint_path and os.path.exists(checkpoint_path):
            self._load_checkpoint()

        # 진행 통계
        self._req_count = 0
        self._start_time = 0.0

    # ------------------------------------------------------------------ #
    # 체크포인트
    # ------------------------------------------------------------------ #
    def _load_checkpoint(self) -> None:
        with open(self.checkpoint_path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n").rstrip("\r")
                if "\t" in line:
                    vw, lid = line.split("\t", 1)
                    self._visited.add((vw, lid))
        logger.info("체크포인트 로드: %d개 노드 이미 방문", len(self._visited))

    async def _mark_visited(self, vw_cd: str, list_id: str) -> None:
        self._visited.add((vw_cd, list_id))
        if self.checkpoint_path:
            async with self._cp_lock:
                with open(self.checkpoint_path, "a", encoding="utf-8") as f:
                    f.write(f"{vw_cd}\t{list_id}\n")

    # ------------------------------------------------------------------ #
    # 저수준 호출 (async)
    # ------------------------------------------------------------------ #
    async def _request(
        self,
        client: httpx.AsyncClient,
        vw_cd: str,
        parent_list_id: str,
    ) -> list[dict[str, Any]]:
        """통계목록 API 한 번 호출. rate limit + 동시성 + 429 백오프 적용."""
        params = {
            "method": "getList",
            "apiKey": self.api_key,
            "format": "json",
            "jsonVD": "Y",
            "vwCd": vw_cd,
            "parentListId": parent_list_id,
        }

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            await self._limiter.acquire()
            try:
                async with self._sem:
                    resp = await client.get(
                        LIST_URL, params=params, timeout=self.timeout
                    )
                self._req_count += 1

                # KOSIS 가 429 를 명시적으로 주는지는 불확실하지만 방어적으로 처리
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning(
                        "429 (vwCd=%s parent=%s) → %.1fs 대기 후 재시도",
                        vw_cd, parent_list_id, wait,
                    )
                    await asyncio.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                last_exc = exc
                wait = min(2 ** attempt, 30)
                logger.warning(
                    "요청 실패 (%d/%d) vwCd=%s parent=%s: %s — %.1fs 후 재시도",
                    attempt, self.retries, vw_cd, parent_list_id, exc, wait,
                )
                await asyncio.sleep(wait)
                continue

            # KOSIS 에러 dict 응답
            if isinstance(data, dict) and ("err" in data or "errMsg" in data):
                raise KosisAPIError(
                    f"{data.get('err', '?')}: {data.get('errMsg', data)}"
                )
            if isinstance(data, dict):
                return [data]
            return data or []

        raise KosisAPIError(f"최대 재시도 초과: {last_exc}")

    # ------------------------------------------------------------------ #
    # 단일 vwCd BFS (계층 단위 동시 호출)
    # ------------------------------------------------------------------ #
    async def crawl_view(
        self,
        client: httpx.AsyncClient,
        vw_cd: str,
        *,
        root_parent_id: str = ROOT_PARENT_ID,
        max_nodes: Optional[int] = None,
    ) -> list[StatTable]:
        """하나의 vwCd 트리를 BFS 로 끝까지 순회.

        같은 깊이(layer)의 부모 노드들을 ``asyncio.gather`` 로 동시 호출한다.
        layer 완료 후 다음 layer 로 진행.
        """
        tables: list[StatTable] = []
        seen_tables: set[tuple[str, str]] = set()
        current_layer: list[str] = [root_parent_id]
        node_count = 0
        layer_idx = 0

        logger.info("[%s] %s 순회 시작", vw_cd, VIEW_CODES.get(vw_cd, ""))

        while current_layer:
            if max_nodes is not None and node_count >= max_nodes:
                logger.info("[%s] max_nodes(%d) 도달 — 중단", vw_cd, max_nodes)
                break

            # 이미 방문한 노드는 제거
            todo = [
                lid for lid in current_layer
                if (vw_cd, lid) not in self._visited
            ]
            if not todo:
                break

            if max_nodes is not None:
                todo = todo[: max(0, max_nodes - node_count)]

            # 계층 동시 호출
            results = await asyncio.gather(
                *[self._request(client, vw_cd, lid) for lid in todo],
                return_exceptions=True,
            )

            next_layer: list[str] = []
            for list_id, result in zip(todo, results):
                await self._mark_visited(vw_cd, list_id)
                node_count += 1

                if isinstance(result, Exception):
                    logger.warning(
                        "[%s] 노드 '%s' 조회 실패: %s", vw_cd, list_id, result
                    )
                    continue

                for node in result:
                    if node.get("TBL_ID"):
                        t = StatTable(
                            vw_cd=vw_cd,
                            org_id=str(node.get("ORG_ID", "")),
                            tbl_id=str(node["TBL_ID"]),
                            tbl_nm=str(node.get("TBL_NM", "")),
                            list_id=list_id,
                        )
                        if t.key() not in seen_tables:
                            seen_tables.add(t.key())
                            tables.append(t)
                    elif node.get("LIST_ID"):
                        child_id = str(node["LIST_ID"])
                        if (vw_cd, child_id) not in self._visited:
                            next_layer.append(child_id)

            layer_idx += 1
            logger.info(
                "[%s] layer %d 완료: 노드 +%d (누적 %d), 통계표 %d개",
                vw_cd, layer_idx, len(todo), node_count, len(tables),
            )
            current_layer = next_layer

        logger.info(
            "[%s] 순회 완료: 노드 %d개, 통계표 %d개",
            vw_cd, node_count, len(tables),
        )
        return tables

    # ------------------------------------------------------------------ #
    # 전체 vwCd 동시 실행
    # ------------------------------------------------------------------ #
    async def crawl_all(
        self,
        view_codes: Optional[Iterable[str]] = None,
        *,
        max_nodes_per_view: Optional[int] = None,
        sequential_views: bool = False,
    ) -> list[StatTable]:
        """모든 vwCd 를 동시에 크롤링. 같은 글로벌 limiter 공유.

        sequential_views=True 면 vwCd 를 하나씩 순차 처리 (디버깅·진행률 가시화용).
        기본은 False = 12개 동시 — limiter 가 천장을 잡으므로 안전.
        """
        if view_codes is None:
            view_codes_list = list(VIEW_CODES.keys())
        else:
            view_codes_list = list(view_codes)

        self._start_time = time.monotonic()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if sequential_views:
                results = []
                for vw_cd in view_codes_list:
                    results.append(
                        await self.crawl_view(
                            client, vw_cd, max_nodes=max_nodes_per_view
                        )
                    )
            else:
                results = await asyncio.gather(
                    *[
                        self.crawl_view(
                            client, vw_cd, max_nodes=max_nodes_per_view
                        )
                        for vw_cd in view_codes_list
                    ]
                )

        # vwCd 간 중복 제거
        all_tables: list[StatTable] = []
        global_seen: set[tuple[str, str]] = set()
        for view_tables in results:
            for t in view_tables:
                if t.key() not in global_seen:
                    global_seen.add(t.key())
                    all_tables.append(t)

        elapsed = time.monotonic() - self._start_time
        rate = self._req_count / elapsed * 60 if elapsed > 0 else 0
        logger.info(
            "전체 순회 완료: 뷰 %d개, 고유 통계표 %d개 / 호출 %d회, "
            "소요 %.1f분, 평균 %.0f req/min",
            len(view_codes_list), len(all_tables),
            self._req_count, elapsed / 60, rate,
        )
        return all_tables

    # ------------------------------------------------------------------ #
    # 저장 유틸 (원본과 동일)
    # ------------------------------------------------------------------ #
    @staticmethod
    def save_csv(tables: list[StatTable], path: str) -> None:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["vwCd", "orgId", "tblId", "tblNm", "listId"])
            for t in tables:
                writer.writerow([t.vw_cd, t.org_id, t.tbl_id, t.tbl_nm, t.list_id])
        logger.info("CSV 저장 완료: %s (%d건)", path, len(tables))

    @staticmethod
    def save_json(tables: list[StatTable], path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump([asdict(t) for t in tables], f, ensure_ascii=False, indent=2)
        logger.info("JSON 저장 완료: %s (%d건)", path, len(tables))


# --------------------------------------------------------------------------- #
# CLI 진입점
# --------------------------------------------------------------------------- #
async def _main_async(args) -> None:
    crawler = KosisListAsyncCrawler(
        timeout=args.timeout,
        retries=args.retries,
        max_per_minute=args.rate,
        concurrency=args.concurrency,
        checkpoint_path=args.checkpoint,
    )
    tables = await crawler.crawl_all(
        view_codes=args.views,
        max_nodes_per_view=args.max_nodes,
        sequential_views=args.sequential_views,
    )
    crawler.save_csv(tables, args.csv)
    if args.json:
        crawler.save_json(tables, args.json)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="KOSIS 통계목록 전체 순회 (async + rate-limited)"
    )
    parser.add_argument(
        "--views",
        nargs="*",
        default=None,
        help=f"순회할 vwCd 목록 (기본: 전체). 선택지: {', '.join(VIEW_CODES)}",
    )
    parser.add_argument(
        "--max-nodes",
        type=int,
        default=None,
        help="뷰별 방문 목록 노드 수 상한 (테스트용).",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=900,
        help="분당 글로벌 호출 상한 (기본 900, KOSIS 제한 1000 의 안전 마진).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=30,
        help="동시 in-flight 요청 수 상한.",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument(
        "--sequential-views",
        action="store_true",
        help="vwCd 를 하나씩 순차 처리 (기본: 12개 동시).",
    )
    parser.add_argument(
        "--checkpoint",
        default="kosis/innnn/kosis_list_async.checkpoint",
        help="이어받기용 체크포인트 파일.",
    )
    parser.add_argument(
        "--csv",
        default="kosis/innnn/kosis_tables_async.csv",
        help="출력 CSV 경로.",
    )
    parser.add_argument("--json", default=None, help="출력 JSON 경로(선택).")
    args = parser.parse_args()

    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
