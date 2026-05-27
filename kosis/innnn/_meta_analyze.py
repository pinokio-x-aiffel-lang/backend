"""1만 표 메타 수집 결과를 분석.

확인 항목:
1. type 별 응답 성공/실패 분포
2. UNIT type 응답 누락률 vs ITM 응답에 UNIT_NM 포함률
3. 단위 정보 최종 커버리지 (둘 중 하나라도 있는 비율)
4. 축산농가 같은 매칭 어려운 표가 샘플에 있는지
5. ITM 응답 크기 분포 (얼마나 풍부한가)
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

JSONL = "kosis/innnn/kosis_meta_sample.jsonl"
LIST_CSV = "kosis/innnn/kosis_tables_async.csv"

rows: list[dict] = []
with open(JSONL, encoding="utf-8") as f:
    for line in f:
        rows.append(json.loads(line))

print(f"총 표 수: {len(rows):,}\n")

# ----- 1. type 별 응답 성공/실패 -----
type_status: dict[str, dict[str, int]] = {
    t: {"ok": 0, "err30": 0, "other_err": 0, "empty": 0}
    for t in ("ITM", "UNIT", "PRD")
}

for r in rows:
    items = r.get("items", {})
    errors = r.get("errors", {})
    for t in ("ITM", "UNIT", "PRD"):
        if t in items:
            v = items[t]
            if not v:
                type_status[t]["empty"] += 1
            elif isinstance(v, list) and len(v) == 0:
                type_status[t]["empty"] += 1
            else:
                type_status[t]["ok"] += 1
        elif t in errors:
            msg = errors[t]
            if "30:" in msg or "데이터가 존재하지 않습니다" in msg:
                type_status[t]["err30"] += 1
            else:
                type_status[t]["other_err"] += 1

print("=== 1. type 별 응답 분포 ===")
print(f"{'type':6s} {'ok':>8s} {'empty':>8s} {'err30':>10s} {'other_err':>10s} | ok률")
for t, s in type_status.items():
    total = sum(s.values())
    ok_rate = s["ok"] / total * 100 if total else 0
    print(
        f"{t:6s} {s['ok']:>8d} {s['empty']:>8d} {s['err30']:>10d} {s['other_err']:>10d} "
        f"| {ok_rate:5.1f}%"
    )

# ----- 2. UNIT 출처별 커버리지 -----
print("\n=== 2. 단위 정보 출처별 커버리지 ===")
unit_type_ok = 0
itm_has_unit = 0
both = 0
either = 0
neither = 0

for r in rows:
    items = r.get("items", {})
    unit_v = items.get("UNIT")
    itm_v = items.get("ITM", [])

    has_unit_type = bool(unit_v) and (
        not isinstance(unit_v, list) or len(unit_v) > 0
    )
    has_unit_in_itm = False
    if isinstance(itm_v, list) and itm_v:
        first = itm_v[0]
        if isinstance(first, dict):
            v = first.get("UNIT_NM") or first.get("UNIT_ID")
            if v and v not in ("", None):
                has_unit_in_itm = True

    if has_unit_type:
        unit_type_ok += 1
    if has_unit_in_itm:
        itm_has_unit += 1
    if has_unit_type and has_unit_in_itm:
        both += 1
    if has_unit_type or has_unit_in_itm:
        either += 1
    if not (has_unit_type or has_unit_in_itm):
        neither += 1

n = len(rows)
print(f"UNIT type 호출 성공:      {unit_type_ok:>5d} ({unit_type_ok/n*100:.1f}%)")
print(f"ITM 응답에 UNIT_NM 포함:  {itm_has_unit:>5d} ({itm_has_unit/n*100:.1f}%)")
print(f"둘 다 가짐:               {both:>5d} ({both/n*100:.1f}%)")
print(f"적어도 하나:              {either:>5d} ({either/n*100:.1f}%) ← 단위 확보율")
print(f"둘 다 없음:               {neither:>5d} ({neither/n*100:.1f}%) ← 단위 누락")

# ----- 3. ITM 응답 크기 분포 -----
print("\n=== 3. ITM 응답 항목 수 분포 ===")
itm_sizes = [
    len(r.get("items", {}).get("ITM", []))
    if isinstance(r.get("items", {}).get("ITM"), list) else 0
    for r in rows
]
itm_sizes_nonzero = [s for s in itm_sizes if s > 0]
if itm_sizes_nonzero:
    itm_sorted = sorted(itm_sizes_nonzero)
    n_nz = len(itm_sorted)
    print(f"ITM 비어있지 않은 표: {n_nz}/{len(rows)} ({n_nz/len(rows)*100:.1f}%)")
    print(f"  ITM 항목 수 — 최소/중간/최대: {itm_sorted[0]} / {itm_sorted[n_nz//2]} / {itm_sorted[-1]}")
    # 분위수
    p25 = itm_sorted[n_nz // 4]
    p75 = itm_sorted[3 * n_nz // 4]
    print(f"  ITM 항목 수 — 25%/75% 분위: {p25} / {p75}")

# ----- 4. 케이스 2 검증: 샘플에 축산 관련 표가 있나 -----
print("\n=== 4. '축산' 키워드 표 샘플 포함 여부 ===")
# 원본 CSV에서 우리 샘플 (orgId,tblId)에 해당하는 tblNm 매핑
sample_keys = {(r["orgId"], r["tblId"]) for r in rows}
tbl_nm_by_key: dict[tuple[str, str], str] = {}
with open(LIST_CSV, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        k = (r["orgId"], r["tblId"])
        if k in sample_keys:
            tbl_nm_by_key[k] = r["tblNm"]

chuksan = [
    (k, nm) for k, nm in tbl_nm_by_key.items()
    if "축산" in nm or "가축" in nm
]
print(f"'축산' 또는 '가축' 포함 표: {len(chuksan)}건 (샘플 1만 중)")
for k, nm in chuksan[:5]:
    print(f"  org={k[0]} tbl={k[1]:25s} {nm}")
if len(chuksan) > 5:
    print(f"  ... 외 {len(chuksan)-5}건")

# 그 표들의 ITM 응답 예시 1건 출력
if chuksan:
    target_key = chuksan[0][0]
    for r in rows:
        if (r["orgId"], r["tblId"]) == target_key:
            print(f"\n  예시 표 ITM 메타: org={target_key[0]} tbl={target_key[1]} ({chuksan[0][1]})")
            itm = r["items"].get("ITM", [])
            print(f"  ITM 항목 수: {len(itm) if isinstance(itm, list) else 'N/A'}")
            if isinstance(itm, list) and itm:
                for i, x in enumerate(itm[:5]):
                    obj_nm = x.get("OBJ_NM", "")
                    itm_nm = x.get("ITM_NM", "")
                    unit_nm = x.get("UNIT_NM", "")
                    print(f"    [{i}] OBJ_NM={obj_nm} | ITM_NM={itm_nm} | UNIT_NM={unit_nm}")
            break

# ----- 5. err30 표가 어떤 표인가 (참고용) -----
print("\n=== 5. ITM에서 err30(데이터 없음) 받은 표 샘플 ===")
err_itm_keys: list[tuple[str, str]] = []
for r in rows:
    if "ITM" in r.get("errors", {}):
        err_itm_keys.append((r["orgId"], r["tblId"]))
print(f"ITM err30 표 수: {len(err_itm_keys)}")
for k in err_itm_keys[:5]:
    print(f"  org={k[0]} tbl={k[1]:25s} {tbl_nm_by_key.get(k, '(이름불명)')}")

# ----- 6. 전체 28만 적용 시 시간 견적 -----
print("\n=== 6. 전체 28만 적용 시 시간 견적 ===")
elapsed_min = 33.6  # 실측
sample_n = 10000
all_n = 284989
mult = all_n / sample_n
print(f"3 type 그대로: {elapsed_min*mult/60:.1f}시간")
# 2 type (UNIT 제외)
print(f"2 type (UNIT 제외): 약 {elapsed_min*mult*2/3/60:.1f}시간")
