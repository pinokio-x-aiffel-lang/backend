"""UNIT type 호출이 빈 응답인 표가 왜 그런지 패턴 분석.

UNIT 정상 응답 그룹 vs err30 그룹을 갈라:
1. ITM 에 UNIT_NM 동봉 비율 (상호 배타 가설)
2. orgId 분포 (기관별 정책)
3. tblId prefix 분포
4. ITM 항목 수 / OBJ 다양성
5. ITM 내 UNIT_NM 다양성 (다단위 표인지)
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

# tblNm 매핑 (참고용)
sample_keys = {(r["orgId"], r["tblId"]) for r in rows}
tbl_nm_by_key: dict[tuple[str, str], str] = {}
with open(LIST_CSV, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        k = (r["orgId"], r["tblId"])
        if k in sample_keys:
            tbl_nm_by_key[k] = r["tblNm"]


def classify(r: dict) -> dict:
    """한 표를 분류."""
    items = r.get("items", {})
    errors = r.get("errors", {})

    unit_v = items.get("UNIT")
    unit_ok = bool(unit_v) and (not isinstance(unit_v, list) or len(unit_v) > 0)

    itm_v = items.get("ITM", [])
    itm_units: set[str] = set()
    if isinstance(itm_v, list):
        for x in itm_v:
            if isinstance(x, dict):
                u = x.get("UNIT_NM")
                if u and u not in ("", None):
                    itm_units.add(u)

    return {
        "org_id": r["orgId"],
        "tbl_id": r["tblId"],
        "unit_type_ok": unit_ok,
        "itm_units": itm_units,                  # ITM 내 단위 집합
        "itm_has_unit": len(itm_units) > 0,
        "itm_unit_diversity": len(itm_units),    # ITM 단위 종류 수
        "itm_size": len(itm_v) if isinstance(itm_v, list) else 0,
    }


classed = [classify(r) for r in rows]
ok_group = [c for c in classed if c["unit_type_ok"]]
err_group = [c for c in classed if not c["unit_type_ok"]]

print(f"UNIT type 정상: {len(ok_group):,}  /  빈응답: {len(err_group):,}\n")

# ----- H1. 상호 배타 가설 — ITM 에 UNIT_NM 동봉 비율 -----
print("=== H1. UNIT type 결과별 — ITM 에 UNIT_NM 동봉 비율 ===")
def pct(grp, key):
    n = sum(1 for c in grp if c[key])
    return n, n / len(grp) * 100 if grp else 0

n_ok_itm, p_ok_itm = pct(ok_group, "itm_has_unit")
n_err_itm, p_err_itm = pct(err_group, "itm_has_unit")
print(f"  UNIT type 정상 + ITM 에도 단위 있음: {n_ok_itm:5d} / {len(ok_group):5d} = {p_ok_itm:5.1f}%")
print(f"  UNIT type 빈응답 + ITM 에 단위 있음: {n_err_itm:5d} / {len(err_group):5d} = {p_err_itm:5.1f}%")
print(f"  → ITM 동봉률이 두 그룹 사이 크게 다르면 '상호 배타' 패턴 확인됨")

# ----- H2. orgId 분포 비교 -----
print("\n=== H2. orgId 별 UNIT type 빈응답 비율 (표가 20개 이상인 기관만) ===")
org_stats: dict[str, dict[str, int]] = {}
for c in classed:
    o = c["org_id"]
    s = org_stats.setdefault(o, {"total": 0, "ok": 0})
    s["total"] += 1
    if c["unit_type_ok"]:
        s["ok"] += 1

big_orgs = [(o, s) for o, s in org_stats.items() if s["total"] >= 20]
big_orgs.sort(key=lambda x: x[1]["ok"] / x[1]["total"])
print(f"  (분석 대상 기관: {len(big_orgs)}개)")
print("  -- UNIT type 빈응답률 높은 기관 top 8 --")
for o, s in big_orgs[:8]:
    err_rate = (1 - s["ok"] / s["total"]) * 100
    print(f"    org={o:6s}  total={s['total']:4d}  ok={s['ok']:4d}  빈응답률={err_rate:5.1f}%")
print("  -- UNIT type 정상률 높은 기관 top 5 --")
for o, s in sorted(big_orgs, key=lambda x: -x[1]["ok"]/x[1]["total"])[:5]:
    ok_rate = s["ok"] / s["total"] * 100
    print(f"    org={o:6s}  total={s['total']:4d}  ok={s['ok']:4d}  정상률={ok_rate:5.1f}%")

# ----- H3. tblId prefix 분포 -----
print("\n=== H3. tblId prefix 별 UNIT type 빈응답 비율 ===")
def prefix(tbl: str) -> str:
    return tbl.split("_", 1)[0] if "_" in tbl else tbl[:3]

prefix_stats: dict[str, dict[str, int]] = {}
for c in classed:
    p = prefix(c["tbl_id"])
    s = prefix_stats.setdefault(p, {"total": 0, "ok": 0})
    s["total"] += 1
    if c["unit_type_ok"]:
        s["ok"] += 1
print(f"  {'prefix':10s} {'total':>6s} {'ok':>6s} {'정상률':>8s}")
for p, s in sorted(prefix_stats.items(), key=lambda x: -x[1]["total"])[:10]:
    rate = s["ok"] / s["total"] * 100
    print(f"  {p:10s} {s['total']:>6d} {s['ok']:>6d} {rate:>7.1f}%")

# ----- H4. ITM 항목 수 비교 -----
print("\n=== H4. ITM 항목 수 그룹별 평균 ===")
def avg(lst): return sum(lst) / len(lst) if lst else 0
ok_sizes = [c["itm_size"] for c in ok_group]
err_sizes = [c["itm_size"] for c in err_group]
print(f"  UNIT type 정상  — ITM 항목 평균={avg(ok_sizes):.0f}  중간값={sorted(ok_sizes)[len(ok_sizes)//2] if ok_sizes else 0}")
print(f"  UNIT type 빈응답 — ITM 항목 평균={avg(err_sizes):.0f}  중간값={sorted(err_sizes)[len(err_sizes)//2] if err_sizes else 0}")

# ----- H5. ITM 내 단위 다양성 (다단위 표 vs 단일단위 표) -----
print("\n=== H5. ITM 내 단위 다양성 (UNIT type 빈응답 그룹만) ===")
err_with_itm_unit = [c for c in err_group if c["itm_has_unit"]]
diversity_counter = Counter(c["itm_unit_diversity"] for c in err_with_itm_unit)
print(f"  분석 대상 (UNIT 빈응답 + ITM 에 단위): {len(err_with_itm_unit)}개")
print(f"  ITM 내 단위 종류 수 분포:")
for div, cnt in sorted(diversity_counter.items())[:8]:
    print(f"    {div}종류: {cnt}개")

# ----- 표본 케이스 보여주기 -----
print("\n=== 6. UNIT 정상 vs 빈응답 — 표 이름 샘플 ===")
print("--- UNIT type 정상 응답 표 5개 ---")
for c in ok_group[:5]:
    nm = tbl_nm_by_key.get((c["org_id"], c["tbl_id"]), "(이름불명)")
    print(f"  org={c['org_id']:6s} {c['tbl_id']:25s} | ITM단위={c['itm_unit_diversity']} | {nm[:50]}")
print("--- UNIT type 빈응답 표 5개 (ITM에는 단위 있음) ---")
err_with_itm = [c for c in err_group if c["itm_has_unit"]]
for c in err_with_itm[:5]:
    nm = tbl_nm_by_key.get((c["org_id"], c["tbl_id"]), "(이름불명)")
    units_sample = list(c["itm_units"])[:3]
    print(f"  org={c['org_id']:6s} {c['tbl_id']:25s} | ITM단위={c['itm_unit_diversity']} ({units_sample}) | {nm[:40]}")
print("--- UNIT type 빈응답 표 5개 (ITM 에도 단위 없음) ---")
err_no_itm = [c for c in err_group if not c["itm_has_unit"]]
for c in err_no_itm[:5]:
    nm = tbl_nm_by_key.get((c["org_id"], c["tbl_id"]), "(이름불명)")
    print(f"  org={c['org_id']:6s} {c['tbl_id']:25s} | {nm[:60]}")
