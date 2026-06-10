"""KOSIS 키워드 검색 recall 탐색 스크립트 — 1단계(탐색).

대표 subject 로 검색해 top 10 을 출력한다.
정답 표를 눈으로 고른다.
그 tbl_id 로 2단계 recall 테스트를 만드는 게 목적이다.

네트워크 + KOSIS_API_KEY(.env) 필요. 키가 없으면 skip.

실행:
    uv run python tests/260609_4_kosis-search-recall_innnn.py          # 전체 출력
    uv run python tests/260609_4_kosis-search-recall_innnn.py 실업률   # 특정 subject만
    uv run pytest tests/260609_4_kosis-search-recall_innnn.py -v       # CI smoke test
"""
from __future__ import annotations

import os
import sys

import pytest
from dotenv import load_dotenv

from src.kosis.search import SearchHit, search_tables

load_dotenv()

TOP_N = 10

# 탐색 대상 claim subject 목록
# → 실행 결과를 보고 정답 tbl_id를 확인한 뒤 GROUND_TRUTH에 채운다
TEST_SUBJECTS = [
    "실업률",
    "합계출산율",
    "경제성장률",
    "소비자물가지수",
    "가계소득",
    "청년실업률",
    "수출액",
    "주택매매가격",
]

# 2단계 자동 검증용 — 탐색 후 정답이 확인된 것만 채운다
# { subject: expected_tbl_id }
GROUND_TRUTH: dict[str, str] = {
    # "실업률": "DT_1DA7002S",  # 확인 후 주석 해제
}

pytestmark = pytest.mark.skipif(
    not os.getenv("KOSIS_API_KEY"),
    reason="KOSIS_API_KEY 가 .env 에 없어 live 검색 테스트를 건너뜀",
)


# ── pytest smoke test ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("subject", TEST_SUBJECTS)
def test_search_returns_hits(subject: str):
    """각 subject로 검색했을 때 결과가 1건 이상 나오는지 확인."""
    hits = search_tables(subject, top_n=TOP_N)
    assert hits, f"'{subject}' 검색 결과가 비어 있음"
    assert all(h.tbl_id for h in hits), f"'{subject}' 결과 중 tbl_id 없는 항목 존재"


@pytest.mark.parametrize("subject,expected_tbl_id", GROUND_TRUTH.items())
def test_recall_at_10(subject: str, expected_tbl_id: str):
    """정답 tbl_id가 top 10 안에 포함되는지 검증 (recall@10)."""
    hits = search_tables(subject, top_n=TOP_N)
    tbl_ids = [h.tbl_id for h in hits]
    assert expected_tbl_id in tbl_ids, (
        f"'{subject}' → 정답 표 {expected_tbl_id} 가 top {TOP_N} 안에 없음\n"
        f"실제 결과: {tbl_ids}"
    )


# ── 탐색용 스크립트 출력 ──────────────────────────────────────────────────────

def _print_hits(subject: str, hits: list[SearchHit]) -> None:
    print(f"\n{'─'*60}")
    print(f"검색어: '{subject}'  ({len(hits)}건)")
    print(f"{'─'*60}")
    for rank, h in enumerate(hits, 1):
        print(f"  [{rank:>2}] tbl_id={h.tbl_id}  org={h.org_id}")
        print(f"       표명  : {h.tbl_nm}")
        print(f"       통계명: {h.stat_nm}  |  기관: {h.org_nm}")
        print(f"       최근치: {h.prd_de}")


if __name__ == "__main__":
    if not os.getenv("KOSIS_API_KEY"):
        raise SystemExit("KOSIS_API_KEY 가 .env 에 없습니다.")

    targets = sys.argv[1:] if len(sys.argv) > 1 else TEST_SUBJECTS

    for subject in targets:
        hits = search_tables(subject, top_n=TOP_N)
        _print_hits(subject, hits)

    print(f"\n{'='*60}")
    print("탐색 완료. 정답 표를 확인한 뒤 GROUND_TRUTH 딕셔너리에 tbl_id를 채우세요.")
    print("  예) GROUND_TRUTH = { '실업률': 'DT_XXXXX', ... }")
