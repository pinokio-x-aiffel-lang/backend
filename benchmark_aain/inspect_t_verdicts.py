"""최종 verdict=T 케이스 검증 — precision[T] + 개별 T 케이스 표.

"분포에 T가 있다"를 넘어 "T 판정이 옳은가(true-T vs false-T)"를 본다.
- precision[T] = (pred T & gold T) / (pred T, gold 라벨 있는 것)  ← false-T 탐지
- recall[T]    = (pred T & gold T) / (gold T)
- 각 T 케이스: 문장 · claim값 · KOSIS값 · 표 · gold · 판정(✅true / ❌false-T / —no-gold)

gold = benchmark/data/7_metric/7_source_2.jsonl (gold_verdict_stage7, 독립 출처).
실행: uv run python benchmark_aain/inspect_t_verdicts.py <capture.jsonl>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "benchmark/data/7_metric/7_source_2.jsonl"
CAP = Path(sys.argv[1]) if len(sys.argv) > 1 else None


def load(p):
    return [json.loads(s) for ln in Path(p).read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def main():
    cap = load(CAP)
    gold = {(r["row_id"], r["claim_id"]): r.get("gold_verdict_stage7")
            for r in load(GOLD) if r.get("scorable")}

    # capture: (row_id, claim_id) -> claim_result + sentence
    t_cases = []
    pred_T = gold_T = tp = 0
    for r in cap:
        rid = r["row_id"]
        snap = r["snapshots"].get("after9", {})
        sent = {c["claim_id"]: c.get("sentence", "") for c in (snap.get("claims") or [])}
        for cr in ((snap.get("verifications") or {}).get("claim_results") or []):
            key = (rid, cr["claim_id"])
            g = gold.get(key)
            if g == "T":
                gold_T += 1
            if cr.get("verdict") == "T":
                pred_T += 1
                if g == "T":
                    tp += 1
                t_cases.append({
                    "row": rid, "cid": cr["claim_id"], "sent": sent.get(cr["claim_id"], "")[:50],
                    "claim_v": cr.get("claim_value"), "kosis_v": cr.get("kosis_value"),
                    "tbl": ((cr.get("metric") or {}).get("compare_id")
                            or (cr.get("evidence") or [{}])[0].get("table_name", ""))[:24] if cr.get("evidence") else "",
                    "gold": g or "—",
                    "mark": "✅true-T" if g == "T" else ("❌false-T" if g in ("F", "N") else "—no-gold"),
                })

    scored = [c for c in t_cases if c["gold"] != "—"]
    prec = tp / len(scored) if scored else None
    rec = tp / gold_T if gold_T else None

    print(f"=== T verdict 검증 — capture {CAP.name} ===")
    print(f"pred T 총 {pred_T}건 (gold 라벨 있는 것 {len(scored)})  |  gold T 총 {gold_T}")
    print(f"precision[T] = {tp}/{len(scored)} = {prec:.3f}" if prec is not None else "precision[T] = n/a")
    print(f"recall[T]    = {tp}/{gold_T} = {rec:.3f}" if rec is not None else "recall[T] = n/a")
    fp = [c for c in scored if c["mark"].startswith("❌")]
    print(f"false-T (pred T but gold≠T) = {len(fp)}건  ← precision-first 위반 여부 핵심")
    print()
    print("| row | claim | 문장 | claim값 | KOSIS값 | gold | 판정 |")
    print("|---|---|---|---|---|---|---|")
    for c in sorted(t_cases, key=lambda x: (x["mark"], x["row"])):
        print(f"| {c['row']} | {c['cid']} | {c['sent']} | {c['claim_v']} | {c['kosis_v']} | {c['gold']} | {c['mark']} |")


if __name__ == "__main__":
    main()
