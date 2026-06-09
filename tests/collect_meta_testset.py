"""메타데이터 테스트셋 수집 스크립트.

여러 도메인 키워드로 search_tables 를 돌린다.
중복을 제거한 (org_id, tbl_id, tbl_nm) 30개를 파이썬 리스트로 출력한다.

`uv run x python tests/collect_meta_testset.py`
"""
from __future__ import annotations

from src.kosis import search_tables

# 도메인을 넓게 퍼뜨려 1축/다축·다양한 주기가 섞이도록 키워드 선정.
KEYWORDS = [
    "실업률", "고용률", "합계출산율", "혼인", "이혼",
    "소비자물가지수", "인구", "사망원인", "출생", "경제성장률",
    "수출", "수입", "가계부채", "주택매매가격", "전세가격",
    "임금", "자영업자", "고령인구", "1인가구", "외국인",
    "관광객", "교통사고", "범죄", "에너지소비", "전력소비",
    "미세먼지", "사교육비", "대학진학률", "최저임금", "국내총생산",
]

TARGET = 30
PER_KEYWORD = 3  # 키워드당 상위 N개에서 후보 추출


def main() -> None:
    seen: set[tuple[str, str]] = set()
    rows: list[tuple[str, str, str]] = []

    for kw in KEYWORDS:
        for h in search_tables(kw, top_n=PER_KEYWORD):
            key = (h.org_id, h.tbl_id)
            if not h.org_id or not h.tbl_id or key in seen:
                continue
            seen.add(key)
            rows.append((h.org_id, h.tbl_id, h.tbl_nm))
            if len(rows) >= TARGET:
                break
        if len(rows) >= TARGET:
            break

    print(f"\n# 수집 {len(rows)}건 (키워드 {len(KEYWORDS)}개, 키워드당 상위 {PER_KEYWORD})")
    print("META_TEST_TABLES = [")
    for org_id, tbl_id, tbl_nm in rows:
        print(f'    ("{org_id}", "{tbl_id}"),  # {tbl_nm}')
    print("]")


if __name__ == "__main__":
    main()
