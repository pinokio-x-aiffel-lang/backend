"""오마이뉴스(ohmynews.com) 전용 본문 추출.

본문은 <article class="article_body at_contents"> 안에 <br> 로 끊긴 텍스트로
실리고, 그 사이에 <figure>(사진+캡션)·<table>([편집자말] 안내)가 섞여 있다. 일반
(trafilatura) 경로는 본문 절반가량을 놓치고 사진 캡션(▲…)을 본문에 섞으므로,
컨테이너를 직접 잡아 캡션·편집자말을 제거하고 <br> 를 줄바꿈으로 살린다.

title·published_at 은 표준 메타로 잡히므로 일반 경로에 맡긴다(매체명만 한글화).
"""
from __future__ import annotations

import html
import re
from typing import Optional
from urllib.parse import urlparse

from selectolax.lexbor import LexborHTMLParser

SOURCE = "오마이뉴스"


def is_ohmynews(url: str) -> bool:
    """오마이뉴스 기사 URL 인지."""
    return urlparse(url).netloc.lower().endswith("ohmynews.com")


def extract_content(tree: LexborHTMLParser) -> str:
    """article 본문에서 사진 캡션·편집자말을 제거하고 본문 텍스트를 복구(실패 시 "")."""
    node = tree.css_first("article.article_body")
    if node is None:
        return ""
    # 공유 트리를 건드리지 않도록 본문 서브트리만 분리해 정제한다.
    art = LexborHTMLParser(node.html or "")
    for junk in art.css("figure, table, script, style"):
        junk.decompose()
    text = re.sub(r"(?i)<br\s*/?>", "\n", art.html or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = (line.strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line).strip()


def extract_meta(tree: LexborHTMLParser) -> dict[str, Optional[str]]:
    """매체명만 보정(영문 og:site_name 'ohmynews' → '오마이뉴스')."""
    return {"source": SOURCE}
