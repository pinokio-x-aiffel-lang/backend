"""네이버 뉴스 검색 API — 본문 입력 시 원문 뉴스 기사 URL/발행일을 찾는다.

발행일이 입력되지 않은 '본문 텍스트' 검증에서, 본문으로 만든 쿼리를 네이버 뉴스
검색에 질의해 상위 기사(원문 URL=originallink + 발행일=pubDate)를 돌려준다. 크롤·
본문 일치 검증은 호출부(load_article.resolve_published_at_from_web)가 기존 언론사별
추출기로 처리한다(엉뚱한 기사·원문 source 채택 방지).

네이버를 쓰는 이유: 한국 뉴스 특화·무료(25,000회/일)·기사 발행일(pubDate)을 바로 줌.
키: NAVER_CLIENT_ID · NAVER_CLIENT_SECRET (infisical 주입). 미설정/실패 시 빈 리스트 →
호출부는 발행일을 못 구한 것으로 처리(상대시점 LLM 폴백 차단으로 안전).
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

import requests

logger = logging.getLogger(__name__)

_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"
_TIMEOUT = 10.0
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class NewsHit:
    """네이버 뉴스 검색 결과 1건."""
    url: str               # originallink — 원문 기사 URL(크롤 대상)
    naver_url: str         # link — 네이버뉴스 URL
    pub_date: str | None   # 기사 발행일(YYYY-MM-DD; pubDate 파싱). 실패 시 None
    title: str
    description: str


def build_query(content: str, *, max_len: int = 100) -> str:
    """검색 쿼리 = 본문 첫 문장(특징 스니펫). 원문 기사를 정확히 찾도록 앞부분을 쓴다."""
    text = (content or "").strip()
    if not text:
        return ""
    parts = re.split(r"(?<=다[.])\s|(?<=[.?!])\s", text, maxsplit=1)
    first = (parts[0] if parts else text).strip()
    return first[:max_len]


def _strip_tags(s: str) -> str:
    """네이버 응답의 <b> 강조 태그·HTML 엔티티 제거."""
    return (
        _TAG_RE.sub("", s or "")
        .replace("&quot;", '"').replace("&amp;", "&")
        .replace("&lt;", "<").replace("&gt;", ">").strip()
    )


def _to_iso(rfc822: str) -> str | None:
    """네이버 pubDate(RFC822 'Tue, 15 Apr 2026 08:02:00 +0900') → 'YYYY-MM-DD'. 실패 시 None."""
    try:
        return parsedate_to_datetime(rfc822).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def search_news(query: str, *, num: int = 5) -> list[NewsHit]:
    """네이버 뉴스 검색 → 상위 기사(원문 URL + 발행일). 키 미설정/실패 시 []."""
    cid = os.environ.get("NAVER_CLIENT_ID")
    sec = os.environ.get("NAVER_CLIENT_SECRET")
    if not (cid and sec):
        logger.warning("네이버 검색 스킵: NAVER_CLIENT_ID/NAVER_CLIENT_SECRET 미설정")
        return []
    if not (query or "").strip():
        return []
    try:
        resp = requests.get(
            _ENDPOINT,
            params={"query": query, "display": min(max(num, 1), 10), "sort": "sim"},
            headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        items = resp.json().get("items") or []
    except (requests.RequestException, ValueError) as exc:
        logger.warning("네이버 검색 실패(흡수): %s", exc)
        return []
    hits: list[NewsHit] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        url = it.get("originallink") or it.get("link")
        if not url:
            continue
        hits.append(NewsHit(
            url=url,
            naver_url=it.get("link", ""),
            pub_date=_to_iso(it.get("pubDate", "")),
            title=_strip_tags(it.get("title", "")),
            description=_strip_tags(it.get("description", "")),
        ))
    return hits


def search_article_urls(query: str, *, num: int = 5) -> list[str]:
    """호환용 — 원문 기사 URL 리스트만 반환."""
    return [h.url for h in search_news(query, num=num)]
