"""일반(사이트 무관) 기사 추출 — JSON-LD(schema.org) → OG/메타 → DOM fallback.

네이버·조선처럼 사이트 전용 처리가 없는 기본 경로. title·published_at·source 를
메타에서 뽑고(추출 시 정리까지), 본문은 JSON-LD articleBody 우선, 없으면
trafilatura 로 추출한다.
"""
from __future__ import annotations

import html
import json
from typing import Any, Iterator, Optional
from urllib.parse import urlparse

import trafilatura
from selectolax.lexbor import LexborHTMLParser

# schema.org JSON-LD 에서 기사로 인정할 @type.
_ARTICLE_TYPES = {"NewsArticle", "Article", "Report", "BlogPosting"}


def clean(value: Optional[str]) -> Optional[str]:
    """HTML 엔티티 해제 + 공백 정리. 일부 언론사가 메타태그 값을 이중 인코딩한다."""
    if not value:
        return None
    cleaned = html.unescape(value).strip()
    return cleaned or None


# --------------------------------------------------------------------------- #
# JSON-LD / 메타태그 파싱
# --------------------------------------------------------------------------- #
def _iter_jsonld(tree: LexborHTMLParser) -> Iterator[dict[str, Any]]:
    """모든 <script type=application/ld+json> 블록을 dict 로 풀어 순회한다.

    단일 객체·배열·@graph 래핑을 모두 평탄화한다. 파싱 실패 블록은 건너뛴다.
    """
    for node in tree.css('script[type="application/ld+json"]'):
        raw = node.text()
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, list):
            yield from (d for d in data if isinstance(d, dict))
        elif isinstance(data, dict):
            graph = data.get("@graph")
            if isinstance(graph, list):
                yield from (d for d in graph if isinstance(d, dict))
            else:
                yield data


def jsonld_article(tree: LexborHTMLParser) -> Optional[dict[str, Any]]:
    """JSON-LD 중 @type 이 기사인 첫 객체를 반환한다(없으면 None)."""
    for obj in _iter_jsonld(tree):
        raw_type = obj.get("@type")
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        if any(t in _ARTICLE_TYPES for t in types):
            return obj
    return None


def _meta(tree: LexborHTMLParser, *names: str) -> Optional[str]:
    """주어진 이름들을 우선순위대로 meta[property|name] content 에서 찾는다."""
    for name in names:
        for attr in ("property", "name"):
            node = tree.css_first(f'meta[{attr}="{name}"]')
            if node:
                val = node.attributes.get("content")
                if val and val.strip():
                    return val.strip()
    return None


def _jsonld_publisher(obj: dict[str, Any]) -> Optional[str]:
    """JSON-LD publisher 의 이름을 추출한다(dict.name 또는 문자열)."""
    pub = obj.get("publisher")
    if isinstance(pub, dict):
        name = pub.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    if isinstance(pub, str) and pub.strip():
        return pub.strip()
    return None


# --------------------------------------------------------------------------- #
# 필드별 추출 — JSON-LD → 메타태그 → DOM 순 fallback
# --------------------------------------------------------------------------- #
def extract_title(
    tree: LexborHTMLParser, jsonld: Optional[dict[str, Any]]
) -> Optional[str]:
    if jsonld:
        headline = jsonld.get("headline")
        if isinstance(headline, str) and headline.strip():
            return clean(headline)
    val = _meta(tree, "og:title", "twitter:title")
    if val:
        return clean(val)
    node = tree.css_first("title")
    if node:
        text = node.text(strip=True)
        if text:
            return clean(text)
    return None


def extract_published_at(
    tree: LexborHTMLParser, jsonld: Optional[dict[str, Any]]
) -> Optional[str]:
    if jsonld:
        for key in ("datePublished", "dateCreated", "dateModified"):
            val = jsonld.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    val = _meta(
        tree,
        "article:published_time",
        "og:article:published_time",
        "datePublished",
        "pubdate",
        "date",
    )
    if val:
        return val
    node = tree.css_first("time[datetime]")
    if node:
        dt = node.attributes.get("datetime")
        if dt and dt.strip():
            return dt.strip()
    return None


def extract_source(
    tree: LexborHTMLParser, jsonld: Optional[dict[str, Any]], url: str
) -> Optional[str]:
    val = _meta(tree, "og:site_name")
    if val:
        return clean(val)
    if jsonld:
        pub = _jsonld_publisher(jsonld)
        if pub:
            return clean(pub)
    host = urlparse(url).netloc
    if host.startswith("www."):
        host = host[4:]
    return host or None


def extract_content(jsonld: Optional[dict[str, Any]], page_html: str) -> str:
    """본문 텍스트 추출.

    ① JSON-LD articleBody 가 있으면 그대로 — 발행자가 선언한 가장 깨끗한 본문.
    ② 없으면 trafilatura 로 추출 — 태그/클래스 무관하게 본문 블록을 찾아
       네비·광고·관련기사 등 boilerplate 를 제거한다. (예: 연합뉴스는 articleBody
       가 없어 ② 로 떨어지는데, <article> 태그엔 리드만 있고 본문은 별도 div 에
       있다 — 단순 <p> 수집으론 본문 대부분을 놓침.)

    통계 기사의 표 수치도 claim 후보이므로 include_tables=True.
    """
    if jsonld:
        body = jsonld.get("articleBody")
        if isinstance(body, str) and body.strip():
            return body.strip()
    text = trafilatura.extract(
        page_html,
        include_comments=False,
        include_tables=True,
    )
    return (text or "").strip()
