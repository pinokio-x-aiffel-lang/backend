"""7단계 after(현재 코드) 진단 — T/F recall 이 여전히 낮은 원인 분해.

calculate_metric 은 결정적(LLM 무) → after6 캡처에 재실행해 scorable 행별
gold_verdict_stage7 vs pred, 증거유무, NEI 사유(note)를 교차분석한다.
실행: uv run x python benchmark_aain/diag_stage7_after.py
"""
from __future__ import annotations

import asyncio
import collections
import json
from pathlib import Path

from src.modules.calculate_metric import calculate_metric
from src.schemas.runtime import MasterSchema

ROOT = Path(__file__).resolve().parent.parent
CAP = ROOT / "benchmark_aain/data/260619_capture_v2_snapshots.jsonl"
DATA = ROOT / "benchmark/data"


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def map_v(v):
    return v if v in ("T", "F", "N") else "N"


async def main():
    cap = load(CAP)
    after6 = {r["row_id"]: r["snapshots"]["after6"] for r in cap if r["snapshots"].get("after6")}

    # 재실행: pred verdict + 증거수 + note 캡처
    pred, nev, note = {}, {}, {}
    sem = asyncio.Semaphore(8)

    async def one(rid, snap):
        async with sem:
            ms = MasterSchema.model_validate(snap)
            await calculate_metric(ms)
            for cr in ms.verifications.claim_results:
                pred[(rid, cr.claim_id)] = cr.verdict
                m = cr.metric
                nev[(rid, cr.claim_id)] = len(cr.evidence or [])
                note[(rid, cr.claim_id)] = (m.note if m else None) or ""

    await asyncio.gather(*[one(rid, s) for rid, s in after6.items()])

    rows = [r for r in load(DATA / "7_metric/7_source_2.jsonl") if r.get("scorable")]
    # gold별 교차표
    xtab = collections.defaultdict(collections.Counter)        # gold -> pred Counter
    ev_split = collections.defaultdict(lambda: collections.Counter())  # gold -> {has_ev, no_ev}
    note_by = collections.defaultdict(collections.Counter)     # (gold,pred) -> note 키워드
    for r in rows:
        key = (r["row_id"], r["claim_id"])
        g = r.get("gold_verdict_stage7")
        p = map_v(pred.get(key))
        ev = nev.get(key, 0)
        xtab[g][p] += 1
        ev_split[g]["has_ev" if ev else "no_ev"] += 1
        # NEI/오분류 사유 요약(note 앞 24자)
        if p != g:
            note_by[(g, p)][(note.get(key, "")[:28] or "(빈 note)")] += 1

    print("=== gold_verdict_stage7 × pred (after) ===")
    for g in ("T", "F", "N"):
        tot = sum(xtab[g].values())
        print(f"  gold {g} (n={tot}): {dict(xtab[g])}  | 증거 {dict(ev_split[g])}")
    print("\n=== 오분류 NEI/사유 top (gold→pred: note) ===")
    for (g, p), c in sorted(note_by.items()):
        print(f"  {g}→{p} (n={sum(c.values())}):")
        for nt, k in c.most_common(4):
            print(f"      {k:>3}  {nt}")


if __name__ == "__main__":
    asyncio.run(main())
