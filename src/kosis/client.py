"""KOSIS API 호출.

urlopen + JSON 파싱 + 응답 type 검증.
KOSIS 가 인증 실패 시 list 가 아닌 dict (에러 코드) 반환 — type check 필수
(메모리 kosis-api-response-shape).
"""
from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import urlopen

BASE_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"


class KosisError(Exception):
    """KOSIS 호출 실패 또는 응답 비정상."""


def call_kosis(params: dict, timeout: float = 30.0) -> list[dict]:
    """KOSIS API 호출 → list[dict] 반환.

    Raises:
        KosisError: HTTP non-200, JSON 파싱 실패, 응답이 list 가 아닌 경우.
    """
    url = BASE_URL + "?" + urlencode(params)
    try:
        with urlopen(url, timeout=timeout) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
    except Exception as e:
        raise KosisError(f"호출 실패: {e}") from e

    if status != 200:
        raise KosisError(f"HTTP {status}: {body[:500]}")

    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise KosisError(f"JSON 파싱 실패: {e}; 원본 앞 500자: {body[:500]}") from e

    if not isinstance(data, list):
        raise KosisError(f"리스트 응답 아님 (인증 실패?): {data}")
    return data
