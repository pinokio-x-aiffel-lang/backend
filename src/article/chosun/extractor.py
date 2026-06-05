"""조선일보(및 Arc XP/Fusion 계열) 전용 본문 추출.

조선일보는 Arc Publishing 의 Fusion(React) 프레임워크로 본문을 클라이언트
렌더한다. 정적 HTML 응답에는 본문 <p> 가 없고(0개), 대신 `window.Fusion` 의
`globalContent.content_elements` JSON 배열에 본문이 데이터로 실려 온다. 헤드리스
브라우저 없이 그 JSON 을 파싱해 본문을 복구한다.

title·published_at·source 는 표준 og/JSON-LD 로 추출되므로(일반 경로에서 동작)
이 모듈은 본문(content)만 책임진다.
"""
from __future__ import annotations

import html
import json
import logging
import re
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("article.chosun")

# 본문으로 취급할 content_element 타입.
_TEXT_TYPES = {"text", "header"}


def is_chosun(url: str) -> bool:
    """조선일보(Arc/Fusion) 도메인인지. www·biz 등 서브도메인 포함."""
    host = urlparse(url).netloc.lower()
    return host.endswith("chosun.com")


def _balanced_array(s: str, start: int) -> Optional[str]:
    """s[start] 의 '[' 부터 짝이 맞는 ']' 까지를 반환(문자열 내부 괄호 무시)."""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def _content_elements(page_html: str) -> Optional[list]:
    """Fusion globalContent 의 content_elements 배열을 파싱해 반환."""
    # globalContent 이후 첫 content_elements 가 본문(다른 위젯의 content_elements 회피).
    anchor = page_html.find("globalContent")
    key = page_html.find('"content_elements"', anchor if anchor != -1 else 0)
    if key == -1:
        return None
    bracket = page_html.find("[", key)
    if bracket == -1:
        return None
    raw = _balanced_array(page_html, bracket)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def _plain(value: object) -> str:
    """content 의 인라인 HTML 태그 제거 + 엔티티 해제 + 공백 정리."""
    if not isinstance(value, str):
        return ""
    text = re.sub(r"<[^>]+>", "", value)
    return html.unescape(text).strip()


def extract_content(page_html: str) -> str:
    """window.Fusion content_elements 에서 본문 텍스트를 복구한다(실패 시 "")."""
    elements = _content_elements(page_html)
    if not elements:
        return ""
    parts: list[str] = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        el_type = el.get("type")
        if el_type in _TEXT_TYPES:
            text = _plain(el.get("content", ""))
            if text:
                parts.append(text)
        elif el_type == "list":
            for item in el.get("items", []):
                if isinstance(item, dict):
                    text = _plain(item.get("content", ""))
                    if text:
                        parts.append(f"- {text}")
    return "\n".join(parts).strip()
