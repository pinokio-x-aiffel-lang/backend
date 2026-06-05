"""네이버 셀렉터 정의의 로드/저장 + 적용 헬퍼.

selectors.json 이 단일 진실원천(source of truth)이고, 자동 복구(repair.py)가
검증을 통과한 새 셀렉터로 이 파일을 갱신한다. 추출(extractor.py)과 복구(repair.py)
양쪽이 같은 `apply_selector` 로 값을 꺼낸다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from selectolax.lexbor import LexborHTMLParser

_PATH = Path(__file__).with_name("selectors.json")


def load_selectors() -> dict[str, dict]:
    """selectors.json → {field: {selector, attr}} 매핑."""
    return json.loads(_PATH.read_text(encoding="utf-8"))


def save_selectors(specs: dict[str, dict]) -> None:
    """갱신된 셀렉터 정의를 selectors.json 에 영속화."""
    _PATH.write_text(
        json.dumps(specs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def apply_selector(tree: LexborHTMLParser, spec: dict) -> Optional[str]:
    """{selector, attr} 스펙을 tree 에 적용해 값을 꺼낸다.

    attr 가 비어 있으면 요소 텍스트, 있으면 해당 속성값. 못 찾으면 None.
    """
    selector = spec.get("selector")
    if not selector:
        return None
    node = tree.css_first(selector)
    if node is None:
        return None
    attr = spec.get("attr") or ""
    value = node.attributes.get(attr) if attr else node.text(strip=True)
    if value is None:
        return None
    value = value.strip()
    return value or None
