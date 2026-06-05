"""네이버 셀렉터 자동 복구 — 레이아웃 변경 감지 시 HCX 로 새 셀렉터를 찾는다.

흐름: 축약 HTML + 깨진 필드 목록 → HCX(LlmCaller) → 셀렉터 후보(JSON) →
*실제 페이지(tree)로 검증* → 통과한 필드만 반환. 환각 셀렉터를 막기 위해
"LLM 이 제안 → 현재 페이지에서 실제로 값이 나오는지 확인" 검증을 반드시 거친다.

LLM 호출 규칙(CLAUDE.md): 반드시 LlmCaller 경유, 파라미터는 ModelPreset.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from selectolax.lexbor import LexborHTMLParser

from src.article.naver.selectors import apply_selector
from src.llm.client import LlmError
from src.llm.llm_caller import LlmCaller
from src.llm.model_presets import NAVER_SELECTOR_REPAIR as _P

logger = logging.getLogger("article.naver.repair")

_llm = LlmCaller()

_FIELD_DESC = {
    "title": "기사 제목",
    "published_at": "기사 게시 일시 (예: 2026-06-05 06:42:19)",
    "source": "원 언론사 이름 (예: 시사IN, 연합뉴스)",
}
# 게시일 후보가 날짜 형태인지 검증하는 최소 패턴.
_DATE_RE = re.compile(r"\d{4}[-./]\d{1,2}")

_SYSTEM = (
    "너는 HTML 에서 특정 정보가 담긴 요소를 CSS 셀렉터로 찾아주는 도구다.\n"
    "네이버 뉴스 기사 페이지의 (축약된) HTML 이 주어진다. 요청된 각 필드에 대해 "
    "그 값을 담고 있는 요소의 CSS 셀렉터와 속성명을 찾아라.\n"
    "- 값이 속성에 있으면 attr 에 속성명(data-date-time, alt, content 등)을, "
    "요소의 텍스트면 attr 를 빈 문자열로 둔다.\n"
    "- 가능한 한 안정적인 셀렉터(id, data-*, 의미 있는 class)를 고른다.\n"
    "마크다운 없이 순수 JSON 만 출력한다."
)


def _reduce_html(page_html: str, limit: int = 12000) -> str:
    """script/style 제거 + 공백 압축 후 앞부분만. 헤더(제목·일시·언론사)는 상단에 있다."""
    stripped = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1>", " ", page_html, flags=re.I | re.S
    )
    collapsed = re.sub(r"\s+", " ", stripped)
    return collapsed[:limit]


def _parse_fields(text: str) -> Optional[list[dict]]:
    """LLM 응답 텍스트(마크다운 펜스 허용) → fields 리스트."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    fields = data.get("fields") if isinstance(data, dict) else None
    return fields if isinstance(fields, list) else None


def repair_selectors(
    page_html: str, tree: LexborHTMLParser, failed_fields: list[str]
) -> Optional[dict[str, dict]]:
    """깨진 필드의 새 셀렉터를 HCX 로 찾아 검증한 뒤 반환한다.

    Returns:
        {field: {selector, attr}} — 실제 페이지 검증을 통과한 필드만. 하나도 못
        고치거나 LLM 호출이 실패하면 None(호출부가 부분 결과로 degrade).
    """
    desc = "\n".join(f"- {f}: {_FIELD_DESC.get(f, f)}" for f in failed_fields)
    user = (
        f"다음 필드가 담긴 요소를 찾아줘:\n{desc}\n\n"
        '출력(JSON): {"fields":[{"field":"...","selector":"...","attr":"...","value":"..."}]}\n'
        "value 에는 그 셀렉터로 실제 읽히는 값을 넣어라.\n\n"
        f"HTML:\n{_reduce_html(page_html)}"
    )
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]
    try:
        resp = _llm.chat(
            _P.model_alias,
            _P.model_name,
            messages,
            max_tokens=_P.max_tokens,
            temperature=_P.temperature,
        )
    except LlmError as exc:
        logger.warning("셀렉터 복구 LLM 호출 실패: %s", exc)
        return None

    proposals = _parse_fields(resp.text)
    if not proposals:
        logger.warning("셀렉터 복구 응답 파싱 실패: %r", resp.text[:200])
        return None

    validated: dict[str, dict] = {}
    for item in proposals:
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        if field not in failed_fields:
            continue
        spec = {"selector": item.get("selector") or "", "attr": item.get("attr") or ""}
        got = apply_selector(tree, spec)  # 현재 페이지에서 실제로 값이 나오는지 검증
        if not got:
            continue
        if field == "published_at" and not _DATE_RE.search(got):
            continue
        validated[field] = spec
        logger.info("필드 %s 복구 검증 통과: %s -> %r", field, spec, got)

    return validated or None
