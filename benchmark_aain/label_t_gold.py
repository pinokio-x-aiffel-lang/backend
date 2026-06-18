"""T행 절대값 gold_tbl_id — 패밀리별 정본 표에서 KOSIS raw 값 대조 라벨링 (병인님 방식·비순환).

비순환: 표는 내가 KOSIS 검색으로 판단해 식별한 정본(아래 라우팅), 값은 raw call_kosis 로 직접 대조.
        파이프라인 함수(map_claim_to_cell_query) 미사용. 내 기억 tbl_id 미사용(검색으로 찾음).
값 일치 셀만 기록(value_confirmed). 복수 표 일치=ambiguous, 미일치=unconfirmed (지어내지 않음).

실행: uv run x python benchmark_aain/label_t_gold.py
출력: benchmark_aain/data/gold_t_confirmed.jsonl  (검토용)
"""
from __future__ import annotations

import json
from pathlib import Path

from src.kosis import KosisError, call_kosis, fetch_table_metadata, resolve_api_key, search_tables

ROOT = Path(__file__).resolve().parent.parent
SSOT = ROOT / "benchmark/data/260614_master_eval_213_parsed_human_checked_SSOT.jsonl"
OUT = ROOT / "benchmark_aain/data/gold_t_confirmed.jsonl"

# 내가 KOSIS 검색으로 식별한 정본 표 후보(패밀리). 값으로 최종 확인.
EMP = ["DT_1DA7002S", "DT_1DA7001S", "DT_1DA7024S", "DT_1DA7012S"]   # 경활총괄/취업자/고용률/실업률(연령·성)
RATE = ["DT_1DA7102S"]                                                # 성/연령별 실업률
WORK = ["DT_1DA7011S", "DT_1DA7029S"]                                 # 취업시간별 취업자(근로자수)
IND = ["DT_1DA7E43S", "INH_2OEEM2005", "DT_1DA9003S"]                 # 산업별 취업자(제조/건설/보건)
RESTED = ["DT_1DA7147S"]                                               # 연령/활동상태별(쉬었음) 비경활
POP = ["DT_1BPA002", "DT_1BPA003", "DT_1BPA001", "DT_2KAA202"]        # 추계인구/부양비
BIRTH = ["DT_1B8000G", "DT_1B8000F", "INH_1B8000F_01", "DT_2KAA207",
         "DT_1B81A21", "DT_1B80A03", "DT_1B8000H"]                    # 인구동향/합계출산율/출생/출산순위
CPI = ["DT_2IFS002", "DT_1J22002"]                                     # 소비자물가지수
_DELTA = ("증감", "전년", "전월", "대비", "상승률")


def route(item: str) -> list[str]:
    if any(k in item for k in ("출산", "출생", "첫째")):
        return BIRTH
    if "물가" in item:
        return CPI
    if "부양비" in item or "인구" in item:
        return POP
    if "쉬었음" in item:
        return RESTED + EMP
    if any(k in item for k in ("제조업", "건설업", "산업", "보건", "도소매", "서비스업")):
        return IND + EMP
    if "근로자" in item or "시간" in item:
        return WORK + EMP
    if "실업률" in item:
        return RATE + EMP
    if any(k in item for k in ("취업자", "고용률", "경제활동", "실업자", "신규채용", "참가율")):
        return EMP + RATE
    return []


def _period(p: str):
    p = str(p or "").strip()
    if not p or "~" in p:
        return None, None
    if "Q" in p.upper():
        y, q = p.upper().replace("-", "").split("Q")[:2]
        return f"{y}Q{q}", "Q"
    if "-" in p:
        a, b = p.split("-")[:2]
        if b.isdigit() and len(b) <= 2:
            return f"{a}{int(b):02d}", "M"
        return a, "Y"
    return p, "Y"


def _close(a, b):
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= max(0.05, abs(b) * 0.01)


_meta_cache: dict = {}
_rows_cache: dict = {}


def fetch_rows(org, tbl, period, pse, api_key):
    key = (tbl, period)
    if key in _rows_cache:
        return _rows_cache[key]
    if tbl not in _meta_cache:
        _meta_cache[tbl] = fetch_table_metadata(org, tbl)
    meta = _meta_cache[tbl]
    itm = "+".join(i.itm_id for i in meta.items[:30]) or "ALL"
    params = {"method": "getList", "apiKey": api_key, "itmId": itm, "objL": "ALL",
              "format": "json", "jsonVD": "Y", "prdSe": "H" if pse == "S" else pse,
              "startPrdDe": period, "endPrdDe": period, "orgId": org, "tblId": tbl}
    for n in range(1, min(max(1, len(meta.axes)), 4) + 1):
        params[f"objL{n}"] = "ALL"
    rows = call_kosis(params)
    _rows_cache[key] = rows
    return rows


def confirm(item, period, pse, value, api_key):
    """라우팅된 표들에서 값-일치 셀 탐색."""
    matches = []
    for tbl in route(item):
        org = "101"
        try:
            rows = fetch_rows(org, tbl, period, pse, api_key)
        except (KosisError, ValueError):
            continue
        for r in rows:
            if not isinstance(r, dict) or r.get("PRD_DE") != period:
                continue
            if _close(r.get("DT"), value):
                matches.append({"org_id": org, "tbl_id": tbl, "item_id": r.get("ITM_ID"),
                                "item_nm": r.get("ITM_NM"), "c1": r.get("C1_NM"), "c2": r.get("C2_NM"),
                                "dt": r.get("DT")})
    return matches


def main():
    api_key = resolve_api_key()
    ssot = [json.loads(s) for ln in SSOT.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]
    res = []
    for r in ssot:
        if r["label"] != "T":
            continue
        for gf in (r.get("gold_figures") or []):
            it, v = gf.get("item"), gf.get("value")
            if not it or v is None or isinstance(v, list) or any(d in it for d in _DELTA):
                continue
            pde, pse = _period(gf.get("period"))
            rec = {"row_id": r["row_id"], "item": it, "period": pde, "gold_value": v}
            if not pde:
                rec["status"] = "skip_period"
                res.append(rec); continue
            if not route(it):
                rec["status"] = "no_route"
                res.append(rec); continue
            m = confirm(it, pde, pse, v, api_key)
            tbls = {x["tbl_id"] for x in m}
            rec["matches"] = m
            rec["status"] = ("confirmed" if len(tbls) == 1 else
                             "ambiguous" if len(tbls) > 1 else "unconfirmed")
            res.append(rec)
            mk = {"confirmed": "✓", "ambiguous": "≈", "unconfirmed": "·"}.get(rec["status"], "?")
            best = m[0] if m else None
            print(f"  {mk} row{r['row_id']} {it!r} {pde}={v} → "
                  f"{best['tbl_id'] + '/' + str(best['item_id']) if best else None} {rec['status']}")
    OUT.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in res) + "\n", encoding="utf-8")
    from collections import Counter
    print("\n", dict(Counter(x["status"] for x in res)), "→", OUT.name)


if __name__ == "__main__":
    main()
