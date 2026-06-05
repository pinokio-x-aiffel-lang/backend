"""네이버 뉴스 전용 메타데이터 추출 (title·published_at·source).

네이버는 표준 JSON-LD/OG 에 게시일·원매체를 싣지 않고 자체 마크업을 쓰므로
일반 추출로는 못 잡는다. selectors.json 의 사이트 전용 셀렉터로 뽑되, 네이버가
레이아웃을 바꿔 셀렉터가 깨지면(불변식 위반) HCX 자동 복구를 트리거한다.

본문(content)은 사이트 무관하게 trafilatura 로 뽑히므로 여기서 다루지 않는다
(이 모듈은 네이버 고유 메타만 책임진다).
"""
from __future__ import annotations

import html
import logging
import re
from typing import Optional
from urllib.parse import urlparse

from selectolax.lexbor import LexborHTMLParser

from src.article.naver.repair import repair_selectors
from src.article.naver.selectors import apply_selector, load_selectors, save_selectors

logger = logging.getLogger("article.naver")

# 게시일이 날짜 형태인지(셀렉터가 엉뚱한 값을 잡았는지) 확인하는 최소 패턴.
_DATE_RE = re.compile(r"\d{4}[-./]\d{1,2}")

# 현재 셀렉터 정의(메모리 캐시). 자동 복구 성공 시 갱신·영속화한다.
_selectors = load_selectors()

# 셀렉터가 깨졌는데 복구도 실패하면, 같은 셀렉터로 매 요청 HCX 를 재호출하지
# 않도록 막는다(비용 방지). 프로세스 재시작 또는 복구 성공 시 다시 시도 가능.
_repair_blocked = False


def is_naver(url: str) -> bool:
    """네이버 뉴스 기사 URL 인지. (n.news / m.news / news).naver.com 매칭."""
    host = urlparse(url).netloc.lower()
    return host.endswith("naver.com") and "news" in host


def _clean(value: Optional[str]) -> Optional[str]:
    """HTML 엔티티 해제 + 공백 정리."""
    if not value:
        return None
    cleaned = html.unescape(value).strip()
    return cleaned or None


def _extract(tree: LexborHTMLParser) -> dict[str, Optional[str]]:
    return {
        field: _clean(apply_selector(tree, spec))
        for field, spec in _selectors.items()
    }


def _broken_fields(meta: dict[str, Optional[str]]) -> list[str]:
    """불변식 위반 필드. 네이버 기사면 title·published_at·source 가 반드시 있어야 한다."""
    broken: list[str] = []
    if not meta.get("title"):
        broken.append("title")
    pub = meta.get("published_at")
    if not pub or not _DATE_RE.search(pub):
        broken.append("published_at")
    if not meta.get("source"):
        broken.append("source")
    return broken


def extract_meta(
    url: str, tree: LexborHTMLParser, page_html: str
) -> dict[str, Optional[str]]:
    """네이버 기사에서 title·published_at·source 추출 (+ 셀렉터 자가복구).

    셀렉터로 1차 추출 → 불변식 위반(레이아웃 변경 의심) 감지 시:
      1) HCX 로 새 셀렉터를 제안받아 실제 페이지로 검증,
      2) 통과하면 selectors.json 갱신 + 현재 요청 즉시 재추출(런타임 복구),
      3) 실패하면 부분 결과 + 경고(사람 점검 신호), 같은 세션 재호출 차단.

    절대 raise 하지 않는다 — 깨져도 부분 결과로 degrade(파이프라인 중단 방지).
    """
    global _selectors, _repair_blocked

    meta = _extract(tree)
    broken = _broken_fields(meta)
    if not broken:
        return meta

    logger.warning(
        "네이버 메타 이상 — 필드 %s 누락/이상, 레이아웃 변경 의심: %s", broken, url
    )
    if _repair_blocked:
        logger.warning("이번 세션 셀렉터 복구가 이미 실패함 — 부분 결과 반환: %s", url)
        return meta

    new_specs = repair_selectors(page_html, tree, broken)
    if not new_specs:
        _repair_blocked = True
        logger.warning("셀렉터 자동 복구 실패 — 사람 점검 필요(부분 결과 반환): %s", url)
        return meta

    _selectors = {**_selectors, **new_specs}
    save_selectors(_selectors)
    _repair_blocked = False
    logger.warning("셀렉터 자동 복구·갱신 성공 — 필드 %s: %s", list(new_specs), url)
    return _extract(tree)  # 갱신된 셀렉터로 즉시 재추출(런타임 복구)
