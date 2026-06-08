"""KOSIS search 모듈 라이브 테스트 — '고용동향' 검색 시 「경제활동인구조사」 확인.

src/kosis/search.py 의 search_tables 로 KOSIS 통합검색(statisticsSearch.do)을
실제 호출한다. "고용동향"은 통계표명이 아니라 통계청 보도자료명이므로, 검색
결과의 STAT_NM(통계조사명)이 「경제활동인구조사」로 떨어지는지(=원천 통계로
연결되는지)를 검증한다.

네트워크 + KOSIS_API_KEY(.env) 필요. 키가 없으면 skip.

실행:
    uv run pytest tests/test_kosis_search_employment.py -v
    uv run python tests/test_kosis_search_employment.py    # 스크립트로(상세 출력)

대상 모듈: src.kosis.search (search_tables)
작성자: leeaain2027 <leeaain2027@gmail.com>
작성일: 2026-06-08
"""
from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from src.kosis.search import SearchHit, search_tables

load_dotenv()

KEYWORD = "고용동향"
EXPECTED_STAT = "경제활동인구조사"

pytestmark = pytest.mark.skipif(
    not os.getenv("KOSIS_API_KEY"),
    reason="KOSIS_API_KEY 가 .env 에 없어 live 검색 테스트를 건너뜀",
)


def test_search_goyongdonghyang_returns_hits():
    """'고용동향' 검색 → 통계표 후보가 1건 이상 나온다."""
    hits = search_tables(KEYWORD, top_n=5)
    assert hits, "'고용동향' 검색 결과가 비어 있음"
    assert all(isinstance(h, SearchHit) for h in hits)
    assert all(h.tbl_id for h in hits), "tbl_id 가 빈 결과가 있음"


def test_search_goyongdonghyang_maps_to_economically_active_survey():
    """'고용동향' 검색 결과의 통계조사명(STAT_NM)에 「경제활동인구조사」가 포함된다."""
    hits = search_tables(KEYWORD, top_n=5)
    stats = {h.stat_nm for h in hits}
    assert EXPECTED_STAT in stats, (
        f"결과에 「{EXPECTED_STAT}」가 없음. 실제 STAT_NM: {sorted(stats)}"
    )


def test_no_table_literally_named_goyongdonghyang():
    """'고용동향'은 보도자료명이라 표명(TBL_NM)이 정확히 '고용동향'인 표는 없다."""
    hits = search_tables(KEYWORD, top_n=10)
    assert all(h.tbl_nm != KEYWORD for h in hits), (
        f"표명이 정확히 '{KEYWORD}'인 표가 존재함: "
        f"{[h.tbl_nm for h in hits if h.tbl_nm == KEYWORD]}"
    )


if __name__ == "__main__":
    if not os.getenv("KOSIS_API_KEY"):
        raise SystemExit("KOSIS_API_KEY 가 .env 에 없습니다.")
    hits = search_tables(KEYWORD, top_n=5)
    print(f"'{KEYWORD}' 검색 결과 {len(hits)}건:")
    for h in hits:
        print(f"  - {h.tbl_nm}  (org={h.org_id}, tbl={h.tbl_id}, STAT_NM={h.stat_nm})")
    stats = {h.stat_nm for h in hits}
    print(f"\nSTAT_NM 집합: {sorted(stats)}")
    print(f"「{EXPECTED_STAT}」 포함 여부: {EXPECTED_STAT in stats}")
