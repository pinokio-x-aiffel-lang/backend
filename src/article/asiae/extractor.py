"""아시아경제(asiae.co.kr) 전용 본문 추출.

아시아경제는 JSON-LD articleBody 에 본문 전체가 아닌 95자 리드(티저)만 싣는다.
일반 경로는 articleBody 를 본문으로 신뢰하므로 본문이 사실상 통째로 누락된다.
실제 본문은 #txt_area(itemprop=articleBody) 의 <p> 들에 있어, 그 컨테이너에서
사진 캡션(div.article_photo)·부제(div.article_head)·광고(article.ad-area·script)·
관련기사(div.mainnews_add)·저작권 문구를 제거하고 본문 문단만 모은다.

title·published_at·source 는 표준 메타로 잡히므로 일반 경로에 맡긴다.
"""
from __future__ import annotations

from urllib.parse import urlparse

from selectolax.lexbor import LexborHTMLParser

# #txt_area 안에서 본문이 아닌 블록들(사진 캡션·부제·광고·관련기사).
_JUNK = (
    "div.article_photo, div.article_head, article.ad-area, "
    "script, style, div.mainnews_add"
)


def is_asiae(url: str) -> bool:
    """아시아경제 기사 URL 인지."""
    return urlparse(url).netloc.lower().endswith("asiae.co.kr")


def extract_content(tree: LexborHTMLParser) -> str:
    """#txt_area 에서 캡션·광고·관련기사·저작권을 빼고 본문 문단만 모은다(실패 시 "")."""
    node = tree.css_first("#txt_area")
    if node is None:
        return ""
    # 공유 트리를 건드리지 않도록 본문 서브트리만 분리해 정제한다.
    art = LexborHTMLParser(node.html or "")
    for junk in art.css(_JUNK):
        junk.decompose()
    parts: list[str] = []
    for p in art.css("p"):
        text = p.text(strip=True)
        if text and "무단전재" not in text:  # 말미 저작권 문구 제외.
            parts.append(text)
    return "\n".join(parts).strip()
