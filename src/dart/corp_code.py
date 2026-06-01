"""기업명 → corp_code(고유번호 8자리) 해석.

OpenDART 의 거의 모든 API 는 corp_code 를 전제로 하지만, list/재무 API 는
이름 검색을 제공하지 않는다. corpCode.xml(전체 기업 매핑 zip)을 1회 받아
이름→코드 인덱스를 만든다. 전체 목록은 크므로 api_key 기준 lru_cache.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from functools import lru_cache

from src.dart.client import fetch_zip_xml


@lru_cache(maxsize=4)
def _load_corp_index(api_key: str) -> dict[str, list[tuple[str, str]]]:
    """corp_name → [(corp_code, stock_code), ...] 인덱스. (프로세스 내 캐시)"""
    data = fetch_zip_xml("corpCode.xml", {"crtfc_key": api_key})
    root = ET.fromstring(data)
    index: dict[str, list[tuple[str, str]]] = {}
    for el in root.iter("list"):
        name = (el.findtext("corp_name") or "").strip()
        code = (el.findtext("corp_code") or "").strip()
        stock = (el.findtext("stock_code") or "").strip()
        if name and code:
            index.setdefault(name, []).append((code, stock))
    return index


def resolve_corp_code(corp_name: str, api_key: str) -> str | None:
    """정확히 일치하는 기업명의 corp_code 반환. 없으면 None.

    동명 기업이 여러 개면 상장사(stock_code 보유)를 우선한다.
    """
    matches = _load_corp_index(api_key).get(corp_name.strip())
    if not matches:
        return None
    listed = [code for code, stock in matches if stock]
    return listed[0] if listed else matches[0][0]
