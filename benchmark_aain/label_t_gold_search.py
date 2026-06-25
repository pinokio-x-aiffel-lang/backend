"""미충원 T행 gold_tbl_id — KOSIS '검색'으로 후보표 동적 발견 후 raw 값 대조 (비순환).

label_t_gold.py 는 route() 가 하드코딩 도메인만 커버해 38건뿐이었다. 여기선 route 대신
search_tables(item) 로 후보표를 동적으로 찾고, 각 표를 raw call_kosis 로 받아 값이 일치하는
셀을 탐색한다. 값-일치 셀만 기록(지어내지 않음). 복수표=ambiguous, 미일치=unconfirmed.

비순환: 표=KOSIS 검색, 값=raw 직접대조. 파이프라인 map_claim_to_cell 미사용.
대상: 260624_origin_sentence_gold_tblid.json 에서 gold_tbl_id 가 비어있는 T행만.
실행: uv run x python benchmark_aain/label_t_gold_search.py
출력: benchmark_aain/data/labeled_by_claude_kosis_tblid.jsonl  (원본 불변, 신규)
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from src.kosis import KosisError, call_kosis, fetch_table_metadata, resolve_api_key, search_tables

ROOT = Path(__file__).resolve().parent.parent
SSOT = ROOT / "benchmark/data/ssot/260614_master_eval_213_parsed_human_checked_SSOT.jsonl"
MISSING_SRC = ROOT / "benchmark/data/ssot/260624_origin_sentence_gold_tblid.json"
OUT = ROOT / "benchmark_aain/data/labeled_by_claude_kosis_tblid.jsonl"

_DELTA = ("증감", "전년", "전월", "대비", "상승률")
SEARCH_TOP = 10  # item당 검색 후보표 상한


def load(p):
    return [json.loads(s) for ln in Path(p).read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


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


def confirm_via_search(item, period, pse, value, api_key):
    """search_tables 로 후보표를 찾고, 각 표에서 값-일치 셀을 탐색."""
    matches, seen = [], set()
    try:
        hits = search_tables(item, top_n=SEARCH_TOP)
    except (KosisError, ValueError):
        return matches
    for h in hits:
        org, tbl = h.org_id, h.tbl_id
        if not tbl or tbl in seen:
            continue
        seen.add(tbl)
        try:
            rows = fetch_rows(org, tbl, period, pse, api_key)
        except (KosisError, ValueError):
            continue
        for r in rows:
            if not isinstance(r, dict) or r.get("PRD_DE") != period:
                continue
            if _close(r.get("DT"), value):
                matches.append({"org_id": org, "tbl_id": tbl, "tbl_nm": h.tbl_nm,
                                "item_id": r.get("ITM_ID"), "item_nm": r.get("ITM_NM"),
                                "c1": r.get("C1_NM"), "c2": r.get("C2_NM"), "dt": r.get("DT")})
                break  # 표당 한 셀이면 충분
    return matches


def main():
    api_key = resolve_api_key()
    missing = {x["row_id"] for x in json.load(open(MISSING_SRC)) if not x.get("gold_tbl_id")}
    ssot = {r["row_id"]: r for r in load(SSOT)}
    res, done = [], 0
    for rid in sorted(missing):
        r = ssot.get(rid) or {}
        figs = [gf for gf in (r.get("gold_figures") or [])
                if gf.get("item") and gf.get("value") is not None
                and not isinstance(gf.get("value"), list)
                and not any(d in gf["item"] for d in _DELTA)]
        if not figs:
            res.append({"row_id": rid, "status": "no_absolute_figure",
                        "source": "value_confirmed_by_claude_search"})
            done += 1
            print(f"  · row{rid} (절대값 figure 없음)", flush=True)
            continue
        for gf in figs:
            it, v = gf["item"], gf["value"]
            pde, pse = _period(gf.get("period"))
            rec = {"row_id": rid, "item": it, "period": pde, "gold_value": v,
                   "source": "value_confirmed_by_claude_search"}
            if not pde:
                rec["status"] = "skip_period"
                res.append(rec)
                continue
            m = confirm_via_search(it, pde, pse, v, api_key)
            tbls = {x["tbl_id"] for x in m}
            rec["matches"] = m
            rec["status"] = ("confirmed" if len(tbls) == 1 else
                             "ambiguous" if len(tbls) > 1 else "unconfirmed")
            res.append(rec)
            mk = {"confirmed": "✓", "ambiguous": "≈", "unconfirmed": "·"}.get(rec["status"], "?")
            best = m[0]["tbl_id"] if m else None
            print(f"  {mk} row{rid} {it!r} {pde}={v} → {best} {rec['status']}", flush=True)
        done += 1
    OUT.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in res) + "\n", encoding="utf-8")
    print(f"\n미충원 {len(missing)}행 처리 | 상태: {dict(Counter(x['status'] for x in res))}")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
