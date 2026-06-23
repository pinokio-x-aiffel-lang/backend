from __future__ import annotations

import logging
import re
from typing import Optional

import requests
from selectolax.lexbor import LexborHTMLParser

from src.article import asiae, chosun, generic, naver, newstapa, ohmynews
from src.article.websearch import build_query, search_article_urls
from src.schemas.runtime import Article, MasterSchema

logger = logging.getLogger(__name__)

# 발행일을 찾으려 크롤할 검색결과 상한(비용·지연 게이팅).
_SEARCH_CRAWL_CAP = 5

# 일부 언론사가 기본 UA 를 차단하므로 브라우저류 UA 로 요청한다.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_TIMEOUT = 15.0


class LoadArticleError(Exception):
    """기사 적재 실패 — URL 오류·크롤링/파싱 실패 등."""


def _is_url(content: str) -> bool:
    """content 가 기사 URL 형태인지(본문 텍스트가 아닌지) 판별한다."""
    return content.startswith(("http://", "https://"))


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
# 입력 종류별 적재
# --------------------------------------------------------------------------- #
def _load_from_text(content: str) -> Article:
    """본문 전문 입력 — 메타데이터 없이 content 만 담는다(나머지 None)."""
    return Article(
        article_id="art-0001",
        title=None,
        content=content,
        # DUMMY(상대시점 계산 테스트용, =2025년 4월). 형식 YYYY-MM. 실데이터 연결 시 None/추출값으로.
        published_at="2025-04",
        source=None,
    )


def _load_from_url(url: str) -> Article:
    """URL 입력 — 방문해 title·published_at·source·본문을 추출한다.

    네이버는 표준 메타에 게시일·원매체가 없어 사이트 전용 추출(+셀렉터 자가복구).
    그 외엔 일반(JSON-LD/OG) 경로로 뽑은 뒤, 사이트 전용 추출기로 비표준 마크업·JS
    렌더 본문 등을 보정한다(조선·아시아경제·뉴스타파·오마이뉴스).
    """
    page_html = _fetch_html(url)
    tree = LexborHTMLParser(page_html)

    if naver.is_naver(url):
        meta = naver.extract_meta(url, tree, page_html)
        return Article(
            article_id="art-0001",
            title=meta.get("title"),
            content=generic.extract_content(None, page_html),
            published_at=meta.get("published_at"),
            source=meta.get("source"),
            url=url,
        )

    jsonld = generic.jsonld_article(tree)
    article = Article(
        article_id="art-0001",
        title=generic.extract_title(tree, jsonld),
        content=generic.extract_content(jsonld, page_html),
        published_at=generic.extract_published_at(tree, jsonld),
        source=generic.extract_source(tree, jsonld, url),
        url=url,
    )
    _refine_by_site(article, url, tree, page_html)
    return article


def _refine_by_site(
    article: Article, url: str, tree: LexborHTMLParser, page_html: str
) -> None:
    """사이트 전용 추출기로 일반 추출값을 보정한다(전용 값이 있을 때만 덮어쓴다)."""
    if chosun.is_chosun(url):
        # 본문이 JS 렌더라 일반 추출로는 0자 — window.Fusion 으로 복구.
        article.content = chosun.extract_content(page_html) or article.content
    elif asiae.is_asiae(url):
        # JSON-LD articleBody 가 95자 티저뿐 — #txt_area 본문 문단으로 복구.
        article.content = asiae.extract_content(tree) or article.content
    elif newstapa.is_newstapa(url):
        # Editor.js 본문 + 표준 메타에 없는 게시일·매체명 보강.
        article.content = newstapa.extract_content(tree) or article.content
        _overlay(article, newstapa.extract_meta(tree))
    elif ohmynews.is_ohmynews(url):
        # <figure>/[편집자말] 섞인 본문 정제 + 매체명 한글화.
        article.content = ohmynews.extract_content(tree) or article.content
        _overlay(article, ohmynews.extract_meta(tree))


def _overlay(article: Article, meta: dict[str, Optional[str]]) -> None:
    """사이트 전용 메타로 일반 추출값을 덮어쓴다(None/빈 값은 무시)."""
    for field, value in meta.items():
        if value:
            setattr(article, field, value)


# --------------------------------------------------------------------------- #
# 발행일 웹 검색 (본문 입력 + 발행일 미입력 시 폴백)
# --------------------------------------------------------------------------- #
def _norm(s: str) -> str:
    """본문 일치 비교용 — 공백 제거."""
    return re.sub(r"\s+", "", s or "")


def _same_article(src: str, cand: str) -> bool:
    """입력 본문(src)과 크롤한 후보 기사(cand)가 같은 기사인지.

    입력 앞부분 특징 스니펫(공백 무시)이 후보 본문에 들어 있으면 동일 기사로 본다.
    엉뚱한 기사 발행일을 가져오는 것을 막는 안전장치.
    """
    src_n, cand_n = _norm(src), _norm(cand)
    snippet = src_n[:40]
    return len(snippet) >= 15 and snippet in cand_n


def resolve_published_at_from_web(content: str) -> Optional[str]:
    """본문 입력일 때 구글로 원문 기사를 찾아 발행일을 가져온다. 실패 시 None.

    기존 언론사별 크롤러(_load_from_url)를 재사용해 검색 상위 URL 의 발행일을 추출하고,
    본문이 입력과 일치하는 기사만 채택한다(엉뚱한 기사 방지). 동기 함수 — 호출부가
    asyncio.to_thread 로 감싸 비차단 실행한다.
    """
    urls = search_article_urls(build_query(content), num=_SEARCH_CRAWL_CAP)
    for url in urls:
        try:
            cand = _load_from_url(url)
        except LoadArticleError as exc:
            logger.warning("발행일 검색: 크롤 실패 %s — %s", url, exc)
            continue
        published = cand.published_at if isinstance(cand.published_at, str) else None
        if published and _same_article(content, cand.content or ""):
            logger.info("발행일 검색 성공: %s → published_at=%s", url, published)
            return published
    logger.info("발행일 검색: 일치 기사 없음(검색결과 %d건)", len(urls))
    return None


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
          네이버·조선·아시아경제·뉴스타파·오마이뉴스는 사이트 전용 추출(src/article),
          그 외엔 일반 JSON-LD/OG 경로(src/article/generic)를 쓴다.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.

    NOTE: 내부 처리(fetch·파싱)는 전부 동기다. runner 가 `await fn(...)` 으로
    호출하므로 시그니처만 async 로 유지한다(단계 규약).
    """
    content = master_schema.content or ""
    if _is_url(content):
        master_schema.article = _load_from_url(content)
    else:
        master_schema.article = _load_from_text(content)

    # 발행일 우선순위: 사용자 입력/웹서치로 해소한 값(published_at_override) > 크롤/더미값.
    # (상대시점 "지난달/전년"을 기사별 실제 발행일 기준으로 정규화하기 위함.)
    if master_schema.published_at_override:
        master_schema.article.published_at = master_schema.published_at_override
