"""E2E 증거 도달율 + coverage 동시 측정 — 전 파이프라인을 행별로 돌려 claim별 캡처.

claim별 기록: verdict / evidence 셀 유무(len>0) / kosis_value 유무(판정에 쓸 값 도달).
산출:
  - evidence_reach(셀)  = evidence 비어있지 않은 claim / 전체
  - value_reach         = kosis_value 있는 claim / 전체  (= 판정 단계에 값이 도달)
  - coverage            = non-NEI(T/F/M) / 전체          (= 실제 판정 냄)
  - gap(손실)           = value_reach - coverage         (값은 왔는데 NEI로 끝남)

입력: SSOT(jsonl, 'text'). 실행: uv run x python benchmark_aain/e2e_evidence_reach.py [--concurrency K] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

from src.pipeline.events import ResultEvent
from src.pipeline.runner import Pipeline

ROOT = Path(__file__).resolve().parent.parent
SSOT = ROOT / "benchmark/data/ssot/260614_master_eval_213_parsed_human_checked_SSOT.jsonl"
COVERED = {"T", "F", "M"}


def _load(path: Path):
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [(r.get("row_id", i), r["text"]) for i, r in enumerate(rows, 1)]


async def _run_one(idx: int, content: str):
    master = None
    err = None
    try:
        async for ev in Pipeline().run(content):
            if isinstance(ev, ResultEvent):
                master = ev.master_schema
    except Exception as e:
        err = str(e)
    return idx, master, err


async def _run_all(lines, conc: int):
    sem = asyncio.Semaphore(conc)

    async def g(i, c):
        async with sem:
            idx, master, err = await _run_one(i, c)
            if master and master.verifications:
                crs = master.verifications.claim_results or []
                ev = sum(1 for cr in crs if (cr.evidence or []))
                val = sum(1 for cr in crs if cr.kosis_value is not None)
                print(f"[{idx}] claims={len(crs)} ev={ev} val={val} "
                      f"{dict(Counter(cr.verdict for cr in crs))}", flush=True)
            else:
                print(f"[{idx}] FAIL {err}", flush=True)
            return idx, master, err

    return await asyncio.gather(*(g(i, c) for i, c in lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    lines = _load(SSOT)
    if a.limit:
        lines = lines[: a.limit]
    print(f"E2E evidence-reach 측정 — {len(lines)}건, 동시 {a.concurrency}\n", flush=True)

    res = asyncio.run(_run_all(lines, a.concurrency))

    total = ev_reach = val_reach = covered = ok = fail = 0
    dist = Counter()
    for _idx, master, _err in res:
        if not (master and master.verifications):
            fail += 1
            continue
        ok += 1
        for cr in (master.verifications.claim_results or []):
            total += 1
            if cr.evidence or []:
                ev_reach += 1
            if cr.kosis_value is not None:
                val_reach += 1
            if cr.verdict in COVERED:
                covered += 1
            dist[cr.verdict] += 1

    def pct(x):
        return f"{x}/{total} = {x / total:.3f}" if total else "0/0"

    print("\n===== E2E EVIDENCE-REACH vs COVERAGE =====", flush=True)
    print(f"기사(행) 성공/실패: {ok}/{fail}", flush=True)
    print(f"전체 claim 수: {total}", flush=True)
    print(f"verdict 분포: {dict(dist)}", flush=True)
    print(f"evidence_reach(셀 있음): {pct(ev_reach)}", flush=True)
    print(f"value_reach(kosis_value 있음): {pct(val_reach)}", flush=True)
    print(f"coverage(T/F/M): {pct(covered)}", flush=True)
    gap = val_reach - covered
    print(f"gap(값 왔는데 NEI): {gap}/{total} = {gap / total:.3f}" if total else "gap: -", flush=True)


if __name__ == "__main__":
    main()
