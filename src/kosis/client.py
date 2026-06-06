"""KOSIS API 공유 HTTP 레이어.

검색(statisticsSearch.do)·데이터(statisticsParameterData.do) 두 단계가 함께
쓰는 단일 GET 경로. requests.Session + 지수 백오프 재시도 + rate limit +
jsonVD=Y 강제를 한곳에 모은다.

응답 정규화:
  - dict 이고 err/errMsg 포함  → KosisError (인증/요청 오류, fail-loud)
  - list                      → 그대로 반환
  - dict (오류 아님)          → require_list=True 면 KosisError, 아니면 [dict]
    (KOSIS 는 인증 실패 시 list 가 아닌 dict 를 줌 — 메모리 kosis-api-response-shape)

KOSIS 비표준 JSON(값 내부 따옴표)은 jsonVD=Y 로 결정론적 처리한다. json5
관용 파싱(=공개 MCP 방식)으로는 값 내부 따옴표를 못 막음 — 메모리 kosis-jsonvd-required.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from typing import Any, Optional

import requests
from dotenv import load_dotenv

logger = logging.getLogger("kosis")

DATA_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
SEARCH_URL = "https://kosis.kr/openapi/statisticsSearch.do"
META_URL = "https://kosis.kr/openapi/statisticsData.do"  # getMeta(통계표 구조 메타)


class KosisError(Exception):
    """KOSIS 호출 실패 또는 응답 비정상."""


def resolve_api_key(api_key: Optional[str] = None) -> str:
    """KOSIS 인증키 확보. 인자가 있으면 그대로, 없으면 .env 의 KOSIS_API_KEY.

    검색(search)·메타(meta) 등 호출부가 공유하는 단일 키 해석 경로.

    Raises:
        ValueError: 인자에도 .env 에도 키가 없을 때.
    """
    if api_key:
        return api_key
    load_dotenv()
    key = os.getenv("KOSIS_API_KEY")
    if not key:
        raise ValueError(
            "API 키가 없습니다. .env 파일에 KOSIS_API_KEY=... 를 지정하세요."
        )
    return key


class _HttpClient:
    """공유 HTTP 클라이언트. Session·재시도·rate limit 상태를 보유."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        retries: int = 3,
        retry_delay: float = 0.5,
        max_per_minute: int = 900,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay  # 지수 백오프 기준값(초)
        # KOSIS 한도는 1분 1000콜. 여유를 둬 기본 900/min. 0이면 비활성.
        self.max_per_minute = max_per_minute
        self._session = requests.Session()
        self._rate_lock = threading.Lock()
        self._call_times: deque[float] = deque()  # 최근 60초 호출 시각(슬라이딩 윈도우)

    def _apply_rate_limit(self) -> None:
        """최근 60초 호출이 max_per_minute 미만일 때만 즉시 통과.

        동시 호출(to_thread 워커들)에서 안전하도록 lock 으로 게이트한다.
        한도 미만이면 윈도우에 시각만 기록하고 바로 반환(동시성 유지);
        한도에 닿으면 가장 오래된 호출이 윈도우를 벗어날 때까지만 대기한다.
        그래서 시작 간격을 인위적으로 띄우지 않고 I/O 는 겹쳐 돌아간다.
        """
        if self.max_per_minute <= 0:
            return
        with self._rate_lock:
            while True:
                now = time.monotonic()
                while self._call_times and now - self._call_times[0] >= 60.0:
                    self._call_times.popleft()
                if len(self._call_times) < self.max_per_minute:
                    self._call_times.append(now)
                    return
                wait = 60.0 - (now - self._call_times[0])
                logger.debug(
                    "rate limit: %.2fs 대기 (분당 %d 도달)", wait, self.max_per_minute
                )
                time.sleep(max(wait, 0.001))

    def get(
        self,
        url: str,
        params: dict[str, Any],
        *,
        require_list: bool = False,
        timeout: Optional[float] = None,
    ) -> list[dict]:
        """KOSIS GET. format=json + jsonVD=Y 를 강제로 주입(호출자 값이 우선)."""
        params = {"format": "json", "jsonVD": "Y", **params}
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                self._apply_rate_limit()
                t0 = time.perf_counter()
                resp = self._session.get(
                    url, params=params, timeout=timeout or self.timeout
                )
                resp.raise_for_status()
                data = resp.json()
                logger.debug(
                    "KOSIS GET %s (%.3fs)", url.rsplit("/", 1)[-1],
                    time.perf_counter() - t0,
                )
            except (requests.RequestException, json.JSONDecodeError) as exc:
                last_exc = exc
                if attempt < self.retries:
                    wait = self.retry_delay * 2 ** (attempt - 1)  # 지수 백오프
                    logger.warning(
                        "KOSIS 요청 실패 (%d/%d): %s — %.1fs 후 재시도",
                        attempt, self.retries, exc, wait,
                    )
                    time.sleep(wait)
                continue
            if isinstance(data, dict) and ("err" in data or "errMsg" in data):
                raise KosisError(
                    f"{data.get('err', '?')}: {data.get('errMsg', data)}"
                )
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                if require_list:
                    raise KosisError(f"리스트 응답 아님 (인증 실패?): {data}")
                return [data]
            return []
        raise KosisError(f"최대 재시도 초과: {last_exc}")


# 모듈 전역 공유 클라이언트 — Session 재사용 + rate limit 을 호출 전반에 적용.
_DEFAULT_CLIENT = _HttpClient()


def kosis_get(
    url: str,
    params: dict[str, Any],
    *,
    require_list: bool = False,
) -> list[dict]:
    """공유 클라이언트로 KOSIS GET → list[dict].

    Raises:
        KosisError: HTTP non-200, JSON 파싱 실패(재시도 초과), API 오류,
            require_list=True 인데 list 가 아닌 경우.
    """
    return _DEFAULT_CLIENT.get(url, params, require_list=require_list)


def call_kosis(params: dict, timeout: float = 30.0) -> list[dict]:
    """
    값 조회(statisticsParameterData.do              itm/obj/prd

    KOSIS 데이터(statisticsParameterData.do) 호출 → list[dict].

    데이터 조회는 항상 list 응답이어야 하므로 require_list=True.

    Raises:
        KosisError: HTTP non-200, JSON 파싱 실패, 응답이 list 가 아닌 경우.
    """
    return _DEFAULT_CLIENT.get(
        DATA_URL, params, require_list=True, timeout=timeout
    )
