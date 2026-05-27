"""
KOSIS 통계표 메타데이터 수집기 (Async 버전)
============================================

원본 ``kosis/kosis_metadata_crolling.py`` 의 동기·직렬 구현을, list 크롤러
와 동일한 async 패턴(글로벌 rate limiter + semaphore + 429 backoff +
체크포인트) 으로 재작성한 버전이다.

엔드포인트
-----------
    https://kosis.kr/openapi/statisticsData.do?method=getMeta

호출 구조
----------
KOSIS getMeta 는 type 파라미터 1개당 호출 1회를 강제한다 (실측 확인:
type 생략·콤마 묶음 모두 err 30 응답). 따라서 호출 수 = 표 수 × type 수.

병목
-----
KOSIS quota 1,000 req/min 이 하한선. async 가 이걸 깰 수는 없고,
"천장을 99% 활용" 까지만 가능하다.

전략
-----
1. 입력: list 크롤 결과 CSV (``kosis_tables_async.csv``) 의 (orgId, tblId).
2. ``--sample N`` 으로 일부만 처리 가능 (검증용).
3. 표 × type 조합을 모두 코루틴으로 fire, 글로벌 limiter 가 quota 관리.
4. 출력: JSONL — 한 줄에 한 표의 메타 묶음.
5. 체크포인트: 완료한 (orgId, tblId) 를 기록해 이어받기.

실행 예
--------
    # 1만 표 샘플, ITM/UNIT/PRD 3종, 약 30분 예상
    python kosis/innnn/kosis_metadata_crolling_async.py \\
        --input kosis/innnn/kosis_tables_async.csv \\
        --sample 10000 --seed 42 \\
        --types ITM UNIT PRD \\
        --rate 900 --concurrency 30 \\
        --out kosis/innnn/kosis_meta_sample.jsonl \\
        --checkpoint kosis/innnn/kosis_meta.checkpoint
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional

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
logger = logging.getLogger("kosis_meta_async")

META_URL = "https://kosis.kr/openapi/statisticsData.do"

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


class KosisAPIError(RuntimeError):
    """KOSIS API가 에러 응답을 반환했을 때 발생."""


# --------------------------------------------------------------------------- #
# 글로벌 rate limiter — list 크롤러와 동일 구현
# --------------------------------------------------------------------------- #
class AsyncRateLimiter:
    """엄격 주기 limiter. 분당 max_per_period 호출 천장 유지."""

    def __init__(self, max_per_period: float, period: float = 60.0) -> None:
        if max_per_period <= 0:
            raise ValueError("max_per_period must be > 0")
        self.interval = period / max_per_period
        self._next_time = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._next_time - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._next_time = max(now, self._next_time) + self.interval


# --------------------------------------------------------------------------- #
# 결과 클래스
# --------------------------------------------------------------------------- #
@dataclass
class TableMeta:
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


# --------------------------------------------------------------------------- #
# 비동기 수집기
# --------------------------------------------------------------------------- #
class KosisMetadataAsyncCollector:
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
        if api_key is None:
            load_dotenv()
            api_key = os.getenv("KOSIS_API_KEY")
        if not api_key:
            raise ValueError("API 키가 없습니다. .env 의 KOSIS_API_KEY 를 지정하세요.")

        self.api_key = api_key
        self.timeout = timeout
        self.retries = retries
        self.checkpoint_path = checkpoint_path

        self._limiter = AsyncRateLimiter(max_per_minute, period=60.0)
        self._sem = asyncio.Semaphore(concurrency)
        self._cp_lock = asyncio.Lock()

        # 완료한 (orgId, tblId) — 이어받기용
        self._completed: set[tuple[str, str]] = set()
        if checkpoint_path and os.path.exists(checkpoint_path):
            with open(checkpoint_path, encoding="utf-8") as f:
                for line in f:
                    line = line.rstrip("\n").rstrip("\r")
                    if "\t" in line:
                        a, b = line.split("\t", 1)
                        self._completed.add((a, b))
            logger.info("체크포인트 로드: %d 표 이미 완료", len(self._completed))

        self._req_count = 0
        self._start_time = 0.0

    async def _mark_completed(self, org_id: str, tbl_id: str) -> None:
        self._completed.add((org_id, tbl_id))
        if self.checkpoint_path:
            async with self._cp_lock:
                with open(self.checkpoint_path, "a", encoding="utf-8") as f:
                    f.write(f"{org_id}\t{tbl_id}\n")

    # ------------------------------------------------------------------ #
    # 저수준 호출 — list 크롤러의 _request 와 동일 패턴
    # ------------------------------------------------------------------ #
    async def _fetch_meta_item(
        self,
        client: httpx.AsyncClient,
        org_id: str,
        tbl_id: str,
        meta_type: str,
    ) -> Any:
        params = {
            "method": "getMeta",
            "apiKey": self.api_key,
            "format": "json",
            "jsonVD": "Y",
            "orgId": org_id,
            "tblId": tbl_id,
            "type": meta_type,
        }

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            await self._limiter.acquire()
            try:
                async with self._sem:
                    resp = await client.get(META_URL, params=params, timeout=self.timeout)
                self._req_count += 1

                if resp.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning(
                        "429 (org=%s tbl=%s type=%s) → %.1fs 대기",
                        org_id, tbl_id, meta_type, wait,
                    )
                    await asyncio.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                last_exc = exc
                wait = min(2 ** attempt, 30)
                logger.warning(
                    "요청 실패 (%d/%d) org=%s tbl=%s type=%s: %s — %.1fs 후 재시도",
                    attempt, self.retries, org_id, tbl_id, meta_type, exc, wait,
                )
                await asyncio.sleep(wait)
                continue

            if isinstance(data, dict) and ("err" in data or "errMsg" in data):
                raise KosisAPIError(
                    f"{data.get('err', '?')}: {data.get('errMsg', data)}"
                )
            return data

        raise KosisAPIError(f"최대 재시도 초과: {last_exc}")

    # ------------------------------------------------------------------ #
    # 한 표의 모든 type 을 동시 수집
    # ------------------------------------------------------------------ #
    async def fetch_table(
        self,
        client: httpx.AsyncClient,
        org_id: str,
        tbl_id: str,
        meta_types: list[str],
    ) -> TableMeta:
        result = TableMeta(org_id=org_id, tbl_id=tbl_id)

        # 같은 표의 type 들을 동시 호출 (limiter 가 quota 관리)
        results = await asyncio.gather(
            *[self._fetch_meta_item(client, org_id, tbl_id, t) for t in meta_types],
            return_exceptions=True,
        )

        for meta_type, r in zip(meta_types, results):
            if isinstance(r, Exception):
                result.errors[meta_type] = str(r)
            else:
                result.items[meta_type] = r

        return result

    # ------------------------------------------------------------------ #
    # 전체 표 순회 — 동시 처리
    # ------------------------------------------------------------------ #
    async def fetch_many(
        self,
        tables: list[tuple[str, str]],
        meta_types: list[str],
        out_path: str,
        *,
        progress_every: int = 200,
    ) -> int:
        """tables 의 각 (orgId, tblId) 에 대해 meta_types 를 수집하고
        out_path 에 JSONL 로 append 저장. 완료 후 처리 표 수 반환.
        """
        self._start_time = time.monotonic()

        # 이미 완료된 표는 스킵
        todo = [(o, t) for o, t in tables if (o, t) not in self._completed]
        if not todo:
            logger.info("모든 표가 이미 완료됨 (체크포인트 기준).")
            return 0

        logger.info(
            "수집 대상 %d 표 × %d type = %d 호출 예정",
            len(todo), len(meta_types), len(todo) * len(meta_types),
        )

        out_lock = asyncio.Lock()
        out_file = open(out_path, "a", encoding="utf-8")

        async def worker(client: httpx.AsyncClient, org_id: str, tbl_id: str) -> None:
            try:
                meta = await self.fetch_table(client, org_id, tbl_id, meta_types)
                async with out_lock:
                    out_file.write(
                        json.dumps(meta.to_dict(), ensure_ascii=False) + "\n"
                    )
                    out_file.flush()
                await self._mark_completed(org_id, tbl_id)
            except Exception as exc:
                logger.error("표 처리 실패 org=%s tbl=%s: %s", org_id, tbl_id, exc)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # 표 단위 코루틴들을 한꺼번에 띄움. limiter 와 sem 이 자동 조절.
                tasks = [
                    asyncio.create_task(worker(client, o, t)) for o, t in todo
                ]

                # 진행률 로깅
                done_count = 0
                for fut in asyncio.as_completed(tasks):
                    await fut
                    done_count += 1
                    if done_count % progress_every == 0:
                        elapsed = time.monotonic() - self._start_time
                        rate = self._req_count / elapsed * 60 if elapsed > 0 else 0
                        if elapsed > 0:
                            eta_min = (len(todo) - done_count) / (done_count / elapsed * 60)
                        else:
                            eta_min = 0
                        logger.info(
                            "진행 %d/%d 표 (%.1f%%) | %.0f req/min | ETA %.1f분",
                            done_count, len(todo),
                            done_count / len(todo) * 100, rate, eta_min,
                        )
        finally:
            out_file.close()

        elapsed = time.monotonic() - self._start_time
        rate = self._req_count / elapsed * 60 if elapsed > 0 else 0
        logger.info(
            "전체 완료: 표 %d개 / 호출 %d회 / 소요 %.1f분 / 평균 %.0f req/min",
            len(todo), self._req_count, elapsed / 60, rate,
        )
        return len(todo)


# --------------------------------------------------------------------------- #
# 입력 CSV → (orgId, tblId) 리스트
# --------------------------------------------------------------------------- #
def load_tables_from_csv(
    csv_path: str,
    *,
    sample: Optional[int] = None,
    seed: int = 42,
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append((r["orgId"], r["tblId"]))

    if sample is not None and sample < len(rows):
        rng = random.Random(seed)
        sampled = rng.sample(rows, sample)
        logger.info("샘플링: %d → %d 표 (seed=%d)", len(rows), sample, seed)
        return sampled

    return rows


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
async def _main_async(args) -> None:
    tables = load_tables_from_csv(
        args.input, sample=args.sample, seed=args.seed
    )

    collector = KosisMetadataAsyncCollector(
        timeout=args.timeout,
        retries=args.retries,
        max_per_minute=args.rate,
        concurrency=args.concurrency,
        checkpoint_path=args.checkpoint,
    )

    await collector.fetch_many(
        tables=tables,
        meta_types=args.types,
        out_path=args.out,
        progress_every=args.progress_every,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="KOSIS 통계표 메타데이터 수집 (async + rate-limited)"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="(orgId, tblId) 가 든 입력 CSV (예: kosis/innnn/kosis_tables_async.csv)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="입력 CSV 에서 무작위 N 개만 추출 (검증용). 미지정 시 전체.",
    )
    parser.add_argument("--seed", type=int, default=42, help="샘플링 시드")
    parser.add_argument(
        "--types",
        nargs="+",
        default=["ITM", "UNIT", "PRD"],
        help=f"수집할 메타 type 목록. 선택지: {', '.join(META_ITEMS)}",
    )
    parser.add_argument(
        "--rate", type=float, default=900,
        help="분당 글로벌 호출 상한 (KOSIS 1,000/min 안전 마진).",
    )
    parser.add_argument(
        "--concurrency", type=int, default=30,
        help="동시 in-flight 요청 수 상한.",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument(
        "--out",
        default="kosis/innnn/kosis_meta_sample.jsonl",
        help="출력 JSONL 경로 (append 모드).",
    )
    parser.add_argument(
        "--checkpoint",
        default="kosis/innnn/kosis_meta.checkpoint",
        help="이어받기용 체크포인트 파일.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=200,
        help="N 표마다 진행률 로그.",
    )
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    # 무효 type 체크
    for t in args.types:
        if t not in META_ITEMS:
            raise SystemExit(
                f"알 수 없는 메타 type: {t} (선택지: {', '.join(META_ITEMS)})"
            )

    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
