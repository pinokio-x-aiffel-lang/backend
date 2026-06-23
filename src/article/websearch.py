"""구글 Custom Search — 본문 입력 시 원문 기사 URL 후보를 찾는다.

발행일이 입력되지 않은 '본문 텍스트' 검증 요청에서, 본문으로 만든 쿼리를 구글에
질의해 상위 결과 URL 을 돌려준다. 크롤·발행일 추출·본문 일치 검증은 호출부
(load_article.resolve_published_at_from_web)가 기존 언론사별 추출기로 처리한다.

키: GOOGLE_API_KEY · GOOGLE_CSE_ID (infisical 주입). 미설정/실패 시 빈 리스트 →
호출부는 발행일을 못 구한 것으로 처리(상대시점 LLM 폴백 차단으로 안전).
"""
from __future__ import annotations

import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

_ENDPOINT = "https://www.googleapis.com/customsearch/v1"
_TIMEOUT = 10.0


def build_query(content: str, *, max_len: int = 100) -> str:
    """검색 쿼리 = 본문 첫 문장(특징 스니펫). 원문 기사를 정확히 찾도록 앞부분을 쓴다."""
    text = (content or "").strip()
    if not text:
        return ""
    # 한국어 종결('…다.') 또는 일반 문장부호 기준 첫 문장.
    parts = re.split(r"(?<=다[.])\s|(?<=[.?!])\s", text, maxsplit=1)
    first = (parts[0] if parts else text).strip()
    return first[:max_len]


def search_article_urls(query: str, *, num: int = 5) -> list[str]:
    """구글 Custom Search 로 쿼리에 대한 상위 결과 URL 리스트. 키 미설정/실패 시 []."""
    key = os.environ.get("GOOGLE_API_KEY")
    cx = os.environ.get("GOOGLE_CSE_ID")
    if not (key and cx):
        logger.warning("구글 검색 스킵: GOOGLE_API_KEY/GOOGLE_CSE_ID 미설정")
        return []
    if not (query or "").strip():
        return []
    try:
        resp = requests.get(
            _ENDPOINT,
            params={"key": key, "cx": cx, "q": query, "num": min(max(num, 1), 10), "hl": "ko"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        items = resp.json().get("items") or []
    except (requests.RequestException, ValueError) as exc:
        logger.warning("구글 검색 실패(흡수): %s", exc)
        return []
    return [it["link"] for it in items if isinstance(it, dict) and it.get("link")]
