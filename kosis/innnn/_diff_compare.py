"""아인님 결과와 내 async 크롤링 결과를 비교한다."""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

AIN = Path(r"d:\Cursor\Project\AIFFEL thon\kosis-table-data\kosis_tables.csv")
MINE = Path(
    r"d:\Cursor\Project\AIFFEL thon\fake-news-detector\kosis\innnn\kosis_tables_async.csv"
)


def load(p: Path) -> list[dict[str, str]]:
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


ain = load(AIN)
mine = load(MINE)

print(f"아인님 행: {len(ain):,}")
print(f"내 결과 행: {len(mine):,}")
print()

ain_keys = {(r["orgId"], r["tblId"]) for r in ain}
mine_keys = {(r["orgId"], r["tblId"]) for r in mine}

only_mine = mine_keys - ain_keys
only_ain = ain_keys - mine_keys
common = ain_keys & mine_keys

print(f"공통 (orgId, tblId): {len(common):,}")
print(f"내 결과에만 있는 키: {len(only_mine)}")
print(f"아인님에만 있는 키: {len(only_ain)}")
print()

ain_by_key = {(r["orgId"], r["tblId"]): r for r in ain}
mine_by_key = {(r["orgId"], r["tblId"]): r for r in mine}

if only_mine:
    print("=== 내 결과에만 있는 (orgId, tblId) ===")
    for k in sorted(only_mine):
        r = mine_by_key[k]
        print(
            f"  vwCd={r['vwCd']:20s} "
            f"orgId={r['orgId']:6s} "
            f"tblId={r['tblId']:25s} "
            f"listId={r['listId']:30s} "
            f"tblNm={r['tblNm']}"
        )
    print()

if only_ain:
    print("=== 아인님에만 있는 (orgId, tblId) ===")
    for k in sorted(only_ain):
        r = ain_by_key[k]
        print(
            f"  vwCd={r['vwCd']:20s} "
            f"orgId={r['orgId']:6s} "
            f"tblId={r['tblId']:25s} "
            f"listId={r['listId']:30s} "
            f"tblNm={r['tblNm']}"
        )
    print()

# vwCd 라벨 분포 비교
ain_vw = Counter(r["vwCd"] for r in ain)
mine_vw = Counter(r["vwCd"] for r in mine)
print("=== vwCd 라벨 분포 (CSV 행 단위) ===")
header = f"{'vwCd':20s} {'아인님':>12s} {'내결과':>12s} {'차이':>10s}"
print(header)
print("-" * len(header))
for vw in sorted(set(ain_vw) | set(mine_vw)):
    a = ain_vw.get(vw, 0)
    m = mine_vw.get(vw, 0)
    print(f"{vw:20s} {a:12,d} {m:12,d} {m - a:+10d}")
print()

# 동일 키에 대해 tblNm/vwCd/listId 가 다른 케이스가 있는지
diff_label = 0
diff_nm = 0
for k in common:
    a, m = ain_by_key[k], mine_by_key[k]
    if a["vwCd"] != m["vwCd"]:
        diff_label += 1
    if a["tblNm"] != m["tblNm"]:
        diff_nm += 1
print("=== 공통 키 내 라벨/이름 불일치 ===")
print(f"vwCd 라벨이 다른 행: {diff_label:,}")
print(f"tblNm 이 다른 행:   {diff_nm:,}")
