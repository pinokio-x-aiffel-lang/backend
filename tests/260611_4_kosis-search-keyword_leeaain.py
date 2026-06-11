"""[4] KOSIS 통계표 조회 — 키워드 1개로 search_tables 를 직접 돌려본다.

KOSIS 통합검색(statisticsSearch.do)을 감싼 src/kosis/search.py 의 search_tables 를
명령행 키워드로 호출해 후보 통계표를 출력만 한다(파이프라인·LLM 없음). 후보가
어떻게 잡히는지 빠르게 눈으로 확인하는 용도. 키는 `uv run x` 가 주입.

    uv run x python tests/260611_4_kosis-search-keyword_leeaain.py "취업자"
    uv run x python tests/260611_4_kosis-search-keyword_leeaain.py "취업자" 20   # 상위 20개
"""
from __future__ import annotations

import sys

from dotenv import load_dotenv

from src.kosis import KosisError, search_tables

load_dotenv()


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print('사용법: uv run x python tests/260611_4_kosis-search-keyword_leeaain.py "키워드" [개수]')
        sys.exit(1)

    keyword = sys.argv[1].strip()
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    try:
        hits = search_tables(keyword, top_n=top_n)
    except (KosisError, ValueError) as e:
        print(f"검색 실패: {e}")
        sys.exit(1)

    print(f'\n키워드 "{keyword}" → 통계표 {len(hits)}건\n')
    for i, h in enumerate(hits, 1):
        print(f"[{i:2}] {h.tbl_nm}")
        print(f"     orgId={h.org_id} tblId={h.tbl_id} | 통계명(stat_nm)={h.stat_nm or '—'} "
              f"| 기관(org_nm)={h.org_nm or '—'} | 수록기간(prd_de)={h.prd_de or '—'}")


if __name__ == "__main__":
    main()
