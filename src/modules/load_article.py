from __future__ import annotations

import requests
from selectolax.lexbor import LexborHTMLParser

from src.article import chosun, generic, naver
from src.schemas.runtime import Article, MasterSchema

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

    네이버: 사이트 전용 추출(+셀렉터 자가복구). 조선일보(Arc/Fusion): 본문이 JS
    렌더라 window.Fusion 파싱으로 복구. 그 외: 일반(generic) JSON-LD/OG 경로.
    """
    page_html = _fetch_html(url)
    tree = LexborHTMLParser(page_html)

    if naver.is_naver(url):
        # 네이버는 표준 메타에 게시일·원매체가 없어 사이트 전용 추출(+자가복구).
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
    # 조선일보는 본문이 JS 렌더라 일반 추출로는 0자 — window.Fusion 으로 복구하고
    # 실패 시 일반 경로로 fallback.
    if chosun.is_chosun(url):
        body = chosun.extract_content(page_html) or generic.extract_content(jsonld, page_html)
    else:
        body = generic.extract_content(jsonld, page_html)
    return Article(
        article_id="art-0001",
        title=generic.extract_title(tree, jsonld),
        content=body,
        published_at=generic.extract_published_at(tree, jsonld),
        source=generic.extract_source(tree, jsonld, url),
        url=url,
    )


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
          네이버·조선일보는 사이트 전용 추출(src/article), 그 외엔 일반
          JSON-LD/OG 경로(src/article/generic)를 쓴다.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.

    NOTE: 내부 처리(fetch·파싱)는 전부 동기다. runner 가 `await fn(...)` 으로
    호출하므로 시그니처만 async 로 유지한다(단계 규약).
    """
    content = master_schema.content or ""
    if _is_url(content):
        master_schema.article = _load_from_url(content)
    else:
        master_schema.article = _load_from_text(content)
