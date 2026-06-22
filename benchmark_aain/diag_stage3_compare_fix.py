"""stage3 compare_period 수정 효과 — 정규화 레벨(결정적, KOSIS 무).

after6 캡처의 change_rate claim 중 compare_period_raw 가 있는 건에 대해
  old = 캡처된 compare_period.llm_value (발행일 base, 구버그)
  new = _normalize_period(raw, 주시점)  (수정: 주 시점 base)
를 비교하고, '사용 가능'(주 시점과 다르고 유효형식) 비율을 센다.
실행: uv run x python benchmark_aain/diag_stage3_compare_fix.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.modules.normalize_claim import _normalize_period

ROOT = Path(__file__).resolve().parent.parent
CAP = ROOT / "benchmark_aain/data/260619_capture_v2_snapshots.jsonl"
VALID = re.compile(r"\d{4}(?:-\d{2}|-Q[1-4]|-H[12])?$")


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def usable(cp, period):
    return bool(cp) and bool(VALID.match(str(cp))) and str(cp) != str(period)


def main():
    cap = load(CAP)
    n = old_ok = new_ok = changed = 0
    examples = []
    for r in cap:
        a6 = r["snapshots"].get("after6")
        if not a6:
            continue
        for c in (a6.get("claims") or []):
            if c.get("claim_type") != "change_rate":
                continue
            cpv = c.get("compare_period_value") or {}
            raw = (cpv.get("raw") or "").strip()
            if not raw:
                continue
            n += 1
            period = (c.get("period_value") or {}).get("llm_value")
            old = cpv.get("llm_value")
            new = _normalize_period(raw, str(period or "")) or raw
            o, nw = usable(old, period), usable(new, period)
            old_ok += o
            new_ok += nw
            if str(old) != str(new):
                changed += 1
                if len(examples) < 12:
                    examples.append((r["row_id"], c["claim_id"], raw, period, old, new))

    print(f"compare_period_raw 있는 change_rate claim: {n}건")
    print(f"  사용가능(주시점과 다른 유효 baseline)  old={old_ok}  →  new={new_ok}   (+{new_ok - old_ok})")
    print(f"  값이 바뀐 건: {changed}")
    print("\n[예시] row/claim | raw | 주시점 | old → new")
    for rid, cid, raw, period, old, new in examples:
        print(f"  {rid} {cid} | {raw!r} | {period} | {old} → {new}")


if __name__ == "__main__":
    main()
