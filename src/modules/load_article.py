from __future__ import annotations

import html
import json
import logging
from typing import Any, Iterator, Optional
from urllib.parse import urlparse

import requests
import trafilatura
from selectolax.lexbor import LexborHTMLParser

from src.article import naver
from src.schemas.runtime import Article, MasterSchema

logger = logging.getLogger("load_article")

# 일부 언론사가 기본 UA 를 차단하므로 브라우저류 UA 로 요청한다.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_TIMEOUT = 15.0

# schema.org JSON-LD 에서 기사로 인정할 @type.
_ARTICLE_TYPES = {"NewsArticle", "Article", "Report", "BlogPosting"}


class LoadArticleError(Exception):
    """기사 적재 실패 — URL 오류·크롤링/파싱 실패 등."""


def _is_url(content: str) -> bool:
    """content 가 기사 URL 형태인지(본문 텍스트가 아닌지) 판별한다."""
    return content.startswith(("http://", "https://"))


def _clean(value: Optional[str]) -> Optional[str]:
    """HTML 엔티티 해제 + 공백 정리. 일부 언론사가 메타태그 값을 이중 인코딩한다."""
    if not value:
        return value
    cleaned = html.unescape(value).strip()
    return cleaned or None


# --------------------------------------------------------------------------- #
# fetch
# --------------------------------------------------------------------------- #
def _fetch_html(url: str) -> str:
    """URL 을 방문해 HTML 텍스트를 반환한다(동기). 실패 시 LoadArticleError.

    requests 는 charset 없는 text/* 응답을 ISO-8859-1 로 가정하므로, 한글
    사이트(UTF-8·EUC-KR)를 위해 apparent_encoding(본문 기반 감지)으로 보정한다.
    """
    try:
        resp = requests.get(
            url,
            timeout=_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
            allow_redirects=True,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise LoadArticleError(f"기사 fetch 실패: {url} — {exc}") from exc
    resp.encoding = resp.apparent_encoding or resp.encoding
    return resp.text


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


def _jsonld_article(tree: LexborHTMLParser) -> Optional[dict[str, Any]]:
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
def _extract_title(
    tree: LexborHTMLParser, jsonld: Optional[dict[str, Any]]
) -> Optional[str]:
    if jsonld:
        headline = jsonld.get("headline")
        if isinstance(headline, str) and headline.strip():
            return headline.strip()
    val = _meta(tree, "og:title", "twitter:title")
    if val:
        return val
    node = tree.css_first("title")
    if node:
        text = node.text(strip=True)
        if text:
            return text
    return None


def _extract_published_at(
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


def _extract_source(
    tree: LexborHTMLParser, jsonld: Optional[dict[str, Any]], url: str
) -> Optional[str]:
    val = _meta(tree, "og:site_name")
    if val:
        return val
    if jsonld:
        pub = _jsonld_publisher(jsonld)
        if pub:
            return pub
    host = urlparse(url).netloc
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _extract_content(jsonld: Optional[dict[str, Any]], page_html: str) -> str:
    """본문 텍스트 추출.

    ① JSON-LD articleBody 가 있으면 그대로 — 발행자가 선언한 가장 깨끗한 본문.
    ② 없으면 trafilatura 로 추출 — 태그/클래스 무관하게 본문 블록을 찾아
       네비·광고·관련기사 등 boilerplate 를 제거한다. (예: 연합뉴스는 articleBody
       가 없어 ② 로 떨어지는데, <article> 태그엔 리드만 있고 본문은 별도 div 에
       있다 — 단순 <p> 수집으론 본문 대부분을 놓침.)

    favor/precision·table 포함 여부는 다운스트림(claim 추출) 요구에 맞춰 조정한다.
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


# --------------------------------------------------------------------------- #
# pipeline step
# --------------------------------------------------------------------------- #
async def load_article(master_schema: MasterSchema) -> None:
    """
    [1] Article Load

    Input:
        master_schema.content        # 기사 URL 또는 본문 텍스트

    Output:
        master_schema.article

    Responsibility:
        content(URL 또는 본문)를 Article 로 변환해 master_schema.article 에 저장한다.
        - 본문 텍스트 입력: 메타데이터 없이 content 만 담는다(나머지 None).
        - URL 입력: 해당 URL 을 방문해 title·published_at·source·본문을 추출한다.
          네이버 기사면 사이트 전용 추출(src/article/naver), 그 외엔 일반
          JSON-LD/OG 경로를 쓴다.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.

    NOTE: 내부 처리(fetch·파싱)는 전부 동기다. runner 가 `await fn(...)` 으로
    호출하므로 시그니처만 async 로 유지한다(단계 규약).
    """
    content = master_schema.content or ""

    if not _is_url(content):
        # 본문 전문 입력 — 메타데이터는 없음(None).
        master_schema.article = Article(
            article_id="art-0001",
            title=None,
            content=content,
            published_at=None,  # "2024-01-01"
            source=None,
        )
        return

    # URL 입력 — 방문해서 메타데이터·본문을 긁어온다.
    url = content
    page_html = _fetch_html(url)
    tree = LexborHTMLParser(page_html)

    if naver.is_naver(url):
        # 네이버는 표준 메타에 게시일·원매체가 없어 사이트 전용 추출(+자가복구).
        meta = naver.extract_meta(url, tree, page_html)
        master_schema.article = Article(
            article_id="art-0001",
            title=meta.get("title"),
            content=_extract_content(None, page_html),
            published_at=meta.get("published_at"),
            source=meta.get("source"),
            url=url,
        )
        return

    jsonld = _jsonld_article(tree)
    master_schema.article = Article(
        article_id="art-0001",
        title=_clean(_extract_title(tree, jsonld)),
        content=_extract_content(jsonld, page_html),
        published_at=_extract_published_at(tree, jsonld),
        source=_clean(_extract_source(tree, jsonld, url)),
        url=url,
    )
