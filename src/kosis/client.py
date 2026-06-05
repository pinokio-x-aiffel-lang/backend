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
import time
from typing import Any, Optional

import requests

logger = logging.getLogger("kosis")

DATA_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
SEARCH_URL = "https://kosis.kr/openapi/statisticsSearch.do"


class KosisError(Exception):
    """KOSIS 호출 실패 또는 응답 비정상."""


class _HttpClient:
    """공유 HTTP 클라이언트. Session·재시도·rate limit 상태를 보유."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        retries: int = 3,
        retry_delay: float = 0.5,
        rate_limit_delay: float = 1.0,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay  # 지수 백오프 기준값(초)
        self.rate_limit_delay = rate_limit_delay  # 요청 간 최소 간격(초). 0이면 비활성
        self._session = requests.Session()
        self._last_request_time: float = 0.0

    def _apply_rate_limit(self) -> None:
        """마지막 요청 이후 rate_limit_delay 초가 안 지났으면 남은 만큼 대기."""
        if self.rate_limit_delay <= 0:
            return
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            wait = self.rate_limit_delay - elapsed
            logger.debug("rate limit: %.2fs 대기", wait)
            time.sleep(wait)

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
                self._last_request_time = time.time()
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
    """KOSIS 데이터(statisticsParameterData.do) 호출 → list[dict].

    데이터 조회는 항상 list 응답이어야 하므로 require_list=True.

    Raises:
        KosisError: HTTP non-200, JSON 파싱 실패, 응답이 list 가 아닌 경우.
    """
    return _DEFAULT_CLIENT.get(
        DATA_URL, params, require_list=True, timeout=timeout
    )
