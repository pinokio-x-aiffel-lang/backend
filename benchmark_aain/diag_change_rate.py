"""증감(CHANGE_RATE) claim 의 compare_value 결손 원인 분해.

after6 캡처에서 CHANGE_RATE claim 을 골라 compare_period_value / evidence.compare_value
유무를 본다 → #1 이 (a)상류 미추출 인지 (b)stage5 기준셀 조회 None 인지 확정.
실행: uv run x python benchmark_aain/diag_change_rate.py
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAP = ROOT / "benchmark_aain/data/260619_capture_v2_snapshots.jsonl"


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def main():
    cap = load(CAP)
    n_cr = 0
    has_cp_val = 0          # compare_period_value.llm_value 있음
    has_ev_compare = 0      # evidence[0].compare_value 있음
    cp_missing_examples = []
    cell_none_examples = []
    for r in cap:
        a6 = r["snapshots"].get("after6")
        if not a6:
            continue
        claims = {c["claim_id"]: c for c in (a6.get("claims") or [])}
        ev_by = {an["claim_id"]: (an.get("evidences") or []) for an in (a6.get("analysis") or [])}
        for cid, c in claims.items():
            if c.get("claim_type") != "change_rate":
                continue
            n_cr += 1
            cpv = ((c.get("compare_period_value") or {}).get("llm_value") or "").strip()
            evs = ev_by.get(cid) or []
            ev_cv = evs[0].get("compare_value") if evs else None
            if cpv:
                has_cp_val += 1
            if ev_cv is not None:
                has_ev_compare += 1
            # 분류: compare_period 추출됐는데 compare_value 없음 = stage5 기준셀 None
            if cpv and ev_cv is None and evs:
                cell_none_examples.append((r["row_id"], cid, cpv,
                                           (c.get("period_value") or {}).get("llm_value"),
                                           evs[0].get("period"), evs[0].get("kosis_tbl_id")))
            if not cpv:
                cp_missing_examples.append((r["row_id"], cid,
                                            (c.get("compare_period_value") or {}).get("raw")))

    print(f"CHANGE_RATE claim 총 {n_cr}건")
    print(f"  compare_period_value.llm_value 있음: {has_cp_val}")
    print(f"  evidence[0].compare_value 있음:      {has_ev_compare}")
    print(f"\n[원인 A] compare_period 미추출/미정규화 (n={len(cp_missing_examples)}):")
    for ex in cp_missing_examples[:8]:
        print(f"   row {ex[0]} {ex[1]} compare_raw={ex[2]!r}")
    print(f"\n[원인 B] compare_period 있는데 evidence.compare_value None = stage5 기준셀 조회실패 (n={len(cell_none_examples)}):")
    for ex in cell_none_examples[:8]:
        print(f"   row {ex[0]} {ex[1]} cp={ex[2]} period={ex[3]} ev_period={ex[4]} tbl={ex[5]}")


if __name__ == "__main__":
    main()
