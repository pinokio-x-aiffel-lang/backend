"""라벨이 다른 14건이 실제로 양쪽 vwCd 트리에 다 등장하는지 확인.

각 vwCd 의 raw 수집 결과(중복 제거 전)에서 그 14건의 키가 양쪽에 모두
나타나는지 본다.

원래 우리 CSV는 dedup 이 끝난 결과라 이걸로는 검증 불가 →
체크포인트는 노드 단위라 표 단위 라벨 정보는 없음 →
가장 깔끔한 방법: 그 14건 표의 listId 형태를 보고, listId 가 양쪽 트리
스타일을 띠는지 추론.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

AIN = Path(r"d:\Cursor\Project\AIFFEL thon\kosis-table-data\kosis_tables.csv")
MINE = Path(
    r"d:\Cursor\Project\AIFFEL thon\fake-news-detector\kosis\innnn\kosis_tables_async.csv"
)


def load(p: Path) -> dict[tuple[str, str], dict[str, str]]:
    with open(p, encoding="utf-8-sig") as f:
        return {(r["orgId"], r["tblId"]): r for r in csv.DictReader(f)}


ain = load(AIN)
mine = load(MINE)

# 공통 키 중 vwCd 라벨이 다른 14건
diffs = []
for k in ain.keys() & mine.keys():
    if ain[k]["vwCd"] != mine[k]["vwCd"]:
        diffs.append(k)

print(f"vwCd 라벨이 다른 공통 키: {len(diffs)} 건\n")
print(f"{'orgId':6s} {'tblId':25s} {'아인님-vwCd':18s} {'아인님-listId':30s} {'내-vwCd':18s} {'내-listId':30s} {'tblNm'}")
print("-" * 180)
for k in sorted(diffs):
    a, m = ain[k], mine[k]
    print(
        f"{k[0]:6s} {k[1]:25s} "
        f"{a['vwCd']:18s} {a['listId']:30s} "
        f"{m['vwCd']:18s} {m['listId']:30s} "
        f"{a['tblNm'][:50]}"
    )
