"""전체 28만 표 메타 결과(kosis_meta_full.jsonl) 스트리밍 분석.

3.67GB 라 메모리에 다 안 올리고 한 줄씩 처리.

확인:
1. ITM/PRD 응답 성공/실패 분포
2. ITM 에서 추출 가능한 단위 커버리지
3. ITM 항목 수 분포 (백분위)
4. PRD 주기(PRD_SE) 분포
5. 축산/가축 표 수
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

JSONL = "kosis/innnn/kosis_meta_full.jsonl"
LIST_CSV = "kosis/innnn/kosis_tables_async.csv"

n = 0
itm_ok = itm_err = 0
prd_ok = prd_err = 0
unit_covered = 0          # ITM 행 어딘가에 단위 있음
unit_missing = 0
itm_sizes: list[int] = []
prd_se_counter: Counter[str] = Counter()
err_msgs: Counter[str] = Counter()

# 축산/가축 키워드 표 카운트 — tblNm 매핑 필요하므로 키 집합만 모음
chuksan_keys: list[tuple[str, str]] = []

with open(JSONL, encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        r = json.loads(line)
        n += 1
        items = r.get("items", {})
        errors = r.get("errors", {})

        # ITM
        itm = items.get("ITM")
        if "ITM" in errors:
            itm_err += 1
            err_msgs[errors["ITM"][:40]] += 1
        elif isinstance(itm, list) and itm:
            itm_ok += 1
            itm_sizes.append(len(itm))
            # 단위 커버리지: 어떤 행이든 UNIT_NM 있으면
            has_unit = any(
                isinstance(x, dict) and x.get("UNIT_NM") not in (None, "", )
                for x in itm
            )
            if has_unit:
                unit_covered += 1
            else:
                unit_missing += 1
        else:
            itm_err += 1

        # PRD
        prd = items.get("PRD")
        if "PRD" in errors:
            prd_err += 1
        elif prd:
            prd_ok += 1
            # PRD_SE 추출 (dict 또는 list)
            prd_obj = prd[0] if isinstance(prd, list) and prd else prd
            if isinstance(prd_obj, dict):
                prd_se_counter[prd_obj.get("PRD_SE", "?")] += 1
        else:
            prd_err += 1

print(f"총 표: {n:,}\n")

print("=== 1. type 응답 성공률 ===")
print(f"  ITM ok: {itm_ok:,} ({itm_ok/n*100:.2f}%)  /  err/empty: {itm_err:,}")
print(f"  PRD ok: {prd_ok:,} ({prd_ok/n*100:.2f}%)  /  err/empty: {prd_err:,}")

print("\n=== 2. 단위 커버리지 (ITM 응답 내 UNIT_NM 기준) ===")
denom = unit_covered + unit_missing
print(f"  ITM 응답 있는 표 중:")
print(f"    단위 포함: {unit_covered:,} ({unit_covered/denom*100:.2f}%)")
print(f"    단위 없음: {unit_missing:,} ({unit_missing/denom*100:.2f}%)")
print(f"  전체 28만 기준 단위 확보율: {unit_covered/n*100:.2f}%")

print("\n=== 3. ITM 항목 수 분포 ===")
if itm_sizes:
    itm_sizes.sort()
    m = len(itm_sizes)
    def pctl(p): return itm_sizes[min(m - 1, int(m * p))]
    print(f"  표본: {m:,}개")
    print(f"  min={itm_sizes[0]}  p25={pctl(0.25)}  median={pctl(0.5)}  p75={pctl(0.75)}  p95={pctl(0.95)}  max={itm_sizes[-1]}")
    print(f"  평균: {sum(itm_sizes)/m:.1f}")

print("\n=== 4. PRD 수록주기(PRD_SE) 분포 ===")
for se, cnt in prd_se_counter.most_common():
    print(f"  {se:6s}: {cnt:,} ({cnt/prd_ok*100:.1f}%)")

print("\n=== 5. ITM err/empty 메시지 분포 ===")
for msg, cnt in err_msgs.most_common(5):
    print(f"  {cnt:,}건: {msg}")

# 축산/가축 표 (원본 CSV 에서 tblNm 으로 카운트)
print("\n=== 6. '축산'/'가축' 표 수 (전체 28만) ===")
chuksan = 0
samples = []
with open(LIST_CSV, encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        nm = row["tblNm"]
        if "축산" in nm or "가축" in nm:
            chuksan += 1
            if len(samples) < 5:
                samples.append((row["orgId"], row["tblId"], nm))
print(f"  축산/가축 포함 표: {chuksan:,}건")
for o, t, nm in samples:
    print(f"    org={o} tbl={t}: {nm[:50]}")
