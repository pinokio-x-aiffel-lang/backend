"""
KOSIS 통계표 메타데이터 수집기

kosis_tables.csv 의 (orgId, tblId) 를 순회하며, KOSIS 통계표설명
(statisticsData.do, method=getMeta) 서비스에서 8종 메타데이터를 수집한다.

- 수집 대상: WGT(가중치) 제외 8종
    TBL(통계표명칭), ORG(기관명칭), PRD(수록정보), ITM(분류/항목),
    CMMT(주석), UNIT(단위), SOURCE(출처), NCD(자료갱신일)
- 한 통계표당 8개 type 을 비동기로 동시 호출(1세트)하고,
  세트들도 병렬로 처리한다.
- 분당 호출 수 제한(슬라이딩 윈도우) + 동시 호출 수 제한(세마포어).
- 429 / 529 및 네트워크 오류에 대해 지수 백오프 자동 재시도.
- 세트 완료 즉시 JSONL 한 줄로 append (락으로 줄 깨짐 방지).
- 상세 로그(재시도/저장완료 등)는 로그 파일로만 기록하고,
  화면에는 1분마다 호출 수만 출력한다.
- 재시작 시 기존 결과 JSONL을 읽어 완료된 통계표는 건너뛴다(이어쓰기).

주의: KOSIS getMeta 는 type 1개당 1종의 메타데이터만 반환한다.
      (type=ALL 로 전부 받는 동작은 공식 문서에 없음)
"""

import os
import csv
import json
import time
import random
import signal
import asyncio
import logging

import aiohttp
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

load_dotenv()          # 상위 디렉터리의 .env
API_KEY = os.getenv("KOSIS_API_KEY")

BASE_URL = "https://kosis.kr/openapi/statisticsData.do"
CSV_PATH = "260526_result_kosis_tables_crolling_aain.csv"
OUTPUT_JSONL = "kosis_meta_results.jsonl"
COMPLETED_IDX = "kosis_meta_results.completed.idx"  # 완료된 (orgId,tblId) 보조 인덱스
LOG_PATH = "kosis_meta_fetcher.log"

# WGT(가중치) 제외 8종 메타데이터 type
META_TYPES = {
    "TBL":    "통계표명칭",
    "ORG":    "기관명칭",
    "PRD":    "수록정보",
    "ITM":    "분류/항목",
    "CMMT":   "주석",
    "UNIT":   "단위",
    "SOURCE": "출처",
    "NCD":    "자료갱신일",
}

# 레이트 리밋 / 동시성
MAX_PER_MINUTE = 950           # 분당 최대 호출 수
MAX_CONCURRENT_REQUESTS = 30   # 동시 진행 중인 개별 호출 수 상한

# 재시도
MAX_RETRIES = 5
RETRYABLE_STATUS = {429, 529}
BASE_BACKOFF = 1.0             # 기본 백오프(초)
MAX_BACKOFF = 30.0             # 백오프 상한(초)

# 모니터
MONITOR_INTERVAL = 60          # 호출 수 출력 주기(초)


# ---------------------------------------------------------------------------
# 로깅: 상세 로그는 파일로만, 화면(stdout)에는 분당 호출 수만 print 로 출력
# ---------------------------------------------------------------------------

logger = logging.getLogger("kosis")
logger.setLevel(logging.INFO)
_file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
_file_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
)
logger.addHandler(_file_handler)
logger.propagate = False        # 루트 로거로 전파 방지(화면 출력 차단)


# ---------------------------------------------------------------------------
# 레이트 리미터
# ---------------------------------------------------------------------------

class RateLimiter:
    """분당 호출 수를 제한하는 슬라이딩 윈도우 리미터 (호출 1건 단위)."""

    def __init__(self, max_per_minute):
        self.max_per_minute = max_per_minute
        self.window = 60.0
        self.timestamps = []
        self.lock = asyncio.Lock()
        self.total_calls = 0       # 누적 호출 수(재시도 포함)

    async def acquire(self):
        async with self.lock:
            while True:
                now = time.monotonic()
                self.timestamps = [t for t in self.timestamps if now - t < self.window]
                if len(self.timestamps) < self.max_per_minute:
                    self.timestamps.append(now)
                    self.total_calls += 1
                    return
                wait = self.window - (now - self.timestamps[0])
                await asyncio.sleep(max(wait, 0.01))


async def monitor_calls(limiter, interval=MONITOR_INTERVAL):
    """interval초마다 직전 구간/누적 호출 수를 출력."""
    prev = 0
    while True:
        await asyncio.sleep(interval)
        current = limiter.total_calls
        print(f"  ⏱ 최근 {interval}초 호출 수: {current - prev}건 (누적 {current}건)")
        prev = current


# ---------------------------------------------------------------------------
# 호출 로직
# ---------------------------------------------------------------------------

def _backoff_delay(attempt, retry_after=None):
    """재시도 대기 시간. Retry-After 헤더가 있으면 우선 사용."""
    if retry_after is not None:
        try:
            return min(float(retry_after), MAX_BACKOFF)
        except (TypeError, ValueError):
            pass
    delay = min(BASE_BACKOFF * (2 ** attempt), MAX_BACKOFF)
    return delay + random.uniform(0, delay * 0.25)   # 지터


async def fetch_one_meta(session, limiter, sem, api_key, org_id, tbl_id, type_code):
    """단일 type 메타데이터 1건. 레이트 리밋 + 동시성 제한 + 자동 재시도."""
    params = {
        "method": "getMeta",
        "apiKey": api_key,
        "format": "json",
        "type":   type_code,
        "orgId":  org_id,
        "tblId":  tbl_id,
    }

    for attempt in range(MAX_RETRIES + 1):
        async with sem:
            await limiter.acquire()
            try:
                async with session.get(
                    BASE_URL, params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status in RETRYABLE_STATUS:
                        if attempt < MAX_RETRIES:
                            delay = _backoff_delay(attempt, resp.headers.get("Retry-After"))
                            logger.info("↻ %s %s/%s: HTTP %s → %.1fs 후 재시도 "
                                        "(orgId=%s, tblId=%s)",
                                        type_code, attempt + 1, MAX_RETRIES,
                                        resp.status, delay, org_id, tbl_id)
                            await asyncio.sleep(delay)
                            continue
                        return type_code, {"error": f"재시도 소진: HTTP {resp.status}"}

                    resp.raise_for_status()
                    text = await resp.text()
                    try:
                        return type_code, json.loads(text)
                    except json.JSONDecodeError:
                        return type_code, {"error": "JSON 파싱 실패", "raw": text}

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < MAX_RETRIES:
                    delay = _backoff_delay(attempt)
                    logger.info("↻ %s %s/%s: %s → %.1fs 후 재시도 "
                                "(orgId=%s, tblId=%s)",
                                type_code, attempt + 1, MAX_RETRIES,
                                type(e).__name__, delay, org_id, tbl_id)
                    await asyncio.sleep(delay)
                    continue
                return type_code, {"error": f"재시도 소진: {type(e).__name__}: {e}"}

    return type_code, {"error": "알 수 없는 실패"}


async def process_table(session, limiter, sem, out_f, idx_f, write_lock,
                        api_key, org_id, tbl_id, tbl_nm, idx):
    """한 통계표의 8개 type을 동시 호출하고, 완료 즉시 JSONL 한 줄로 기록."""
    tasks = [
        fetch_one_meta(session, limiter, sem, api_key, org_id, tbl_id, type_code)
        for type_code in META_TYPES
    ]
    pairs = await asyncio.gather(*tasks)
    meta = {type_code: data for type_code, data in pairs}

    record = {
        "orgId": org_id,
        "tblId": tbl_id,
        "tblNm": tbl_nm,
        "meta": meta,
    }

    # 한 줄을 미리 직렬화한 뒤, 락 안에서는 write 한 번만 (락 점유 최소화)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    idx_line = f"{org_id},{tbl_id}\n"
    async with write_lock:
        # 본체(JSONL)를 먼저 기록·flush한 뒤 보조 인덱스를 기록한다.
        # 이 순서여야 인덱스에 있는 키는 본체에도 반드시 존재함이 보장된다.
        out_f.write(line)
        out_f.flush()
        idx_f.write(idx_line)
        idx_f.flush()

    logger.info("저장 완료 [%s]: %s (orgId=%s, tblId=%s)",
                idx, tbl_nm, org_id, tbl_id)
    return idx


# ---------------------------------------------------------------------------
# 메인 흐름
# ---------------------------------------------------------------------------

def _rebuild_keys_from_jsonl(jsonl_path):
    """본체 JSONL에서 (orgId, tblId) 집합을 재생성한다(보조 인덱스 폴백용).

    각 줄 앞부분만 부분 파싱하면 빠르지만, 폴백은 드물게만 일어나므로
    정확성을 위해 전체 파싱한다. 깨진 줄은 무시한다.
    """
    completed = set()
    if not os.path.exists(jsonl_path):
        return completed
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                org_id = rec.get("orgId")
                tbl_id = rec.get("tblId")
                if org_id and tbl_id:
                    completed.add((org_id, tbl_id))
            except json.JSONDecodeError:
                continue
    return completed


def load_completed_keys(jsonl_path, idx_path):
    """이미 완료된 (orgId, tblId) 집합을 반환.

    1순위: 가벼운 보조 인덱스 파일(idx_path)을 읽는다(매우 빠름).
    폴백: 보조 인덱스가 없으면 본체 JSONL에서 재생성하고,
          이후 빠른 재시작을 위해 보조 인덱스를 새로 써둔다.

    완료 판정의 최종 근거는 본체 JSONL이며, 보조 인덱스는 그 캐시다.
    """
    # 1순위: 보조 인덱스
    if os.path.exists(idx_path):
        completed = set()
        with open(idx_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",", 1)
                if len(parts) == 2 and parts[0] and parts[1]:
                    completed.add((parts[0], parts[1]))
        return completed

    # 폴백: 본체에서 재생성 (보조 인덱스가 유실/미생성된 경우)
    completed = _rebuild_keys_from_jsonl(jsonl_path)
    if completed:
        # 다음 재시작부터는 빠르게 읽도록 보조 인덱스를 새로 기록
        with open(idx_path, "w", encoding="utf-8") as f:
            for org_id, tbl_id in completed:
                f.write(f"{org_id},{tbl_id}\n")
        logger.info("보조 인덱스 없음 → 본체에서 %s건 재생성 후 기록", len(completed))
    return completed


async def run_from_csv(csv_path, api_key):
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # === 테스트: 데이터 두 번째 행만 처리 (전체 실행 시 이 줄을 삭제) ===
    rows = rows[:]

    # 이미 완료된 통계표는 건너뛴다 (재시작 대비)
    completed = load_completed_keys(OUTPUT_JSONL, COMPLETED_IDX)
    if completed:
        msg = f"재개: 이미 완료된 {len(completed):,}건을 건너뜁니다."
        print(msg)
        logger.info(msg)

    limiter = RateLimiter(MAX_PER_MINUTE)
    sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    write_lock = asyncio.Lock()

    monitor = asyncio.create_task(monitor_calls(limiter))

    count = 0
    skipped = 0
    tasks = []
    try:
        # 이어쓰기 모드: 기존 결과를 보존한 채 뒤에 append
        # 본체(JSONL)와 보조 인덱스를 함께 연다.
        with open(OUTPUT_JSONL, "a", encoding="utf-8") as out_f, \
             open(COMPLETED_IDX, "a", encoding="utf-8") as idx_f:
            async with aiohttp.ClientSession() as session:
                for i, row in enumerate(rows, start=1):
                    org_id = row["orgId"].strip()
                    tbl_id = row["tblId"].strip()
                    tbl_nm = row.get("tblNm", "").strip()

                    if not org_id or not tbl_id:
                        logger.warning("빈 값 건너뜀 [%s]: orgId=%s, tblId=%s",
                                       i, org_id, tbl_id)
                        continue

                    # 이미 완료된 통계표면 호출하지 않고 건너뜀
                    if (org_id, tbl_id) in completed:
                        skipped += 1
                        continue

                    # 진짜 Task 로 만들어 외부에서 취소 가능하게 한다
                    tasks.append(asyncio.ensure_future(
                        process_table(session, limiter, sem, out_f, idx_f, write_lock,
                                      api_key, org_id, tbl_id, tbl_nm, i)
                    ))

                try:
                    # 완료되는 순서대로 진행 (각 task가 자체적으로 JSONL에 기록)
                    for fut in asyncio.as_completed(tasks):
                        await fut
                        count += 1
                except asyncio.CancelledError:
                    # 종료 신호로 취소됨 → 진행 중인 모든 태스크 취소 후 정리
                    print("\n⚠ 종료 신호 감지: 진행 중인 작업을 취소합니다...")
                    logger.warning("종료 신호 감지: 진행 중 작업 취소")
                    for t in tasks:
                        if not t.done():
                            t.cancel()
                    # 취소가 반영되도록 한 번 모아서 대기 (예외는 무시)
                    await asyncio.gather(*tasks, return_exceptions=True)
                    raise
    finally:
        # 어떤 경우에도 모니터는 정리
        monitor.cancel()
        try:
            await monitor
        except asyncio.CancelledError:
            pass
        logger.info("최종 누적 호출 수: %s건 (이번 실행 완료 %s건, 건너뜀 %s건)",
                    limiter.total_calls, count, skipped)

    return count


async def main():
    if not API_KEY:
        raise SystemExit("환경변수 KOSIS_API_KEY 가 설정되지 않았습니다. .env 를 확인하세요.")

    loop = asyncio.get_running_loop()

    # 실제 작업을 별도 태스크로 띄우고, 종료 신호가 오면 이 태스크를 취소한다
    work = asyncio.ensure_future(run_from_csv(CSV_PATH, API_KEY))

    def _request_cancel():
        if not work.done():
            work.cancel()

    # SIGINT(Ctrl+C), SIGTERM 에 핸들러 등록
    # (Windows 등 add_signal_handler 미지원 환경에서는 KeyboardInterrupt 로 폴백)
    handlers_installed = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_cancel)
            handlers_installed.append(sig)
        except NotImplementedError:
            pass

    try:
        count = await work
        print(f"\n완료: 총 {count}개 통계표의 메타데이터를 수집했습니다.")
        print(f"결과 저장: {OUTPUT_JSONL}")
    except asyncio.CancelledError:
        print("중단되었습니다. 그때까지 완료된 결과는 파일에 저장되어 있습니다.")
    except KeyboardInterrupt:
        # add_signal_handler 미지원 환경 폴백
        _request_cancel()
        try:
            await work
        except asyncio.CancelledError:
            pass
        print("중단되었습니다. 그때까지 완료된 결과는 파일에 저장되어 있습니다.")
    finally:
        for sig in handlers_installed:
            loop.remove_signal_handler(sig)


if __name__ == "__main__":
    asyncio.run(main())
