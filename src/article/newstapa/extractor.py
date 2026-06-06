"""뉴스타파(newstapa.org) 전용 추출 — 본문 + 게시일/매체명.

본문은 Editor.js 블록(.ce-paragraph 문단 / .ce-header 소제목)으로 실리고, 게시일·
매체명은 표준 메타에 없다(og:site_name·article:published_time 부재). 그래서 일반
경로로는 본문이 파편만 잡히고 게시일·source 가 비므로 사이트 전용으로 보강한다.

title 은 og:title 로 잡히므로 일반 경로에 맡긴다.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

from selectolax.lexbor import LexborHTMLParser

SOURCE = "뉴스타파"

# ".author-container" 에 "박종화2026년 06월 02일 15시 25분" 처럼 기자명+게시일이
# 한 덩어리로 온다. 숫자만 차례로(연·월·일·시·분) 집어 ISO 로 조립한다.
_DATE_RE = re.compile(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D+(\d{1,2})\D+(\d{1,2})")


def is_newstapa(url: str) -> bool:
    """뉴스타파 기사 URL 인지."""
    return urlparse(url).netloc.lower().endswith("newstapa.org")


def extract_content(tree: LexborHTMLParser) -> str:
    """Editor.js 본문 블록(소제목·문단)을 문서 순서대로 모은다(실패 시 "").

    사진 캡션은 별도 블록 타입이라 .ce-paragraph/.ce-header 에 안 걸려 자연히 빠진다.
    """
    wrap = tree.css_first("#journal_article_wrap")
    if wrap is None:
        return ""
    parts: list[str] = []
    for node in wrap.css(".ce-header, .ce-paragraph"):
        text = node.text(strip=True)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def extract_meta(tree: LexborHTMLParser) -> dict[str, Optional[str]]:
    """게시일·매체명 추출(표준 메타에 없어 사이트 전용)."""
    return {"published_at": _published_at(tree), "source": SOURCE}


def _published_at(tree: LexborHTMLParser) -> Optional[str]:
    """.author-container 의 'YYYY년 MM월 DD일 HH시 MM분' 을 ISO(+09:00)로 변환."""
    node = tree.css_first(".author-container")
    if node is None:
        return None
    m = _DATE_RE.search(node.text())
    if not m:
        return None
    y, mo, d, h, mi = (int(g) for g in m.groups())
    return f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:00+09:00"
