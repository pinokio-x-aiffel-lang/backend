"""3~5단계 퍼널 — from_origin_212_source(2단계 후 claim 212건) 손실 측정.

source 는 이미 2단계 산출물이라 claim 을 그대로 MasterSchema 에 주입하고
  [3] normalize_claim → [4] retrieve_kosis_candidates → [5] fetch_kosis_data
만 돌린다. 각 claim 이 어디서 떨어지는지 센다:

  - 진입 N = 212 claim
  - [4] 손실 = retrieve 후 candidates 0개(표 후보 못 찾음) [+ [4] raise]
  - [5] 손실 = candidates 있으나 evidences 0개(셀 매칭 실패) [+ [5] raise]
  - 최종 생존 = evidences ≥ 1

실행(시크릿 주입):
  uv run x python benchmark/260617_3~5_from-origin-212-funnel_leeaain/260617_3~5_from-origin-212-funnel_leeaain.py [--limit N] [--concurrency K]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter
from pathlib import Path

from src.modules.fetch_kosis_data import fetch_kosis_data
from src.modules.normalize_claim import normalize_claim
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.schemas.runtime import Claim, MasterSchema

HERE = Path(__file__).resolve().parent
BASE = HERE.name
DATA = HERE.parent / "data" / "from_origin_212_source.jsonl"
RESULT_JSON = HERE / f"{BASE}_result.json"
REPORT_MD = HERE / f"{BASE}_report.md"

STEPS = [
    (3, "normalize_claim", normalize_claim),
    (4, "retrieve_kosis_candidates", retrieve_kosis_candidates),
    (5, "fetch_kosis_data", fetch_kosis_data),
]


def _read(path: Path, limit: int) -> list[dict]:
    rows = [
        json.loads(s) for ln in path.read_text(encoding="utf-8").splitlines()
        if (s := ln.strip()).startswith("{")
    ]
    return rows[:limit] if limit else rows


async def _run_one(rec: dict) -> dict:
    claim = Claim.model_validate(rec)
    ms = MasterSchema(content=rec.get("sentence", ""), claims=[claim])
    err_step = err = None
    t0 = time.perf_counter()
    for no, _name, fn in STEPS:
        try:
            await fn(ms)
        except Exception as exc:
            err_step, err = no, f"{type(exc).__name__}: {exc}"
            break
    dur = time.perf_counter() - t0

    n_cand = sum(len(a.candidates) for a in ms.analysis)
    n_ev = sum(len(a.evidences) for a in ms.analysis)

    # 분류
    if err_step is not None:
        status = f"err_stage{err_step}"
    elif n_cand == 0:
        status = "loss_stage4"          # 표 후보 0
    elif n_ev == 0:
        status = "loss_stage5"          # 후보는 있으나 셀 0
    else:
        status = "survived"

    return {
        "claim_id": rec.get("claim_id"), "source_id": rec.get("source_id"),
        "subject": claim.subject, "period_raw": claim.period_value.raw,
        "value_raw": claim.value.raw,
        "n_candidates": n_cand, "n_evidences": n_ev,
        "status": status, "err_step": err_step, "error": err,
        "duration_s": round(dur, 2),
        "sentence": rec.get("sentence", "")[:90],
    }


async def _run_all(rows: list[dict], conc: int) -> list[dict]:
    sem = asyncio.Semaphore(conc)
    total = len(rows)
    done = [0]

    async def guarded(rec):
        async with sem:
            r = await _run_one(rec)
            done[0] += 1
            print(f"[{done[0]:>3}/{total}] {r['status']:12s} "
                  f"cand={r['n_candidates']:>2} ev={r['n_evidences']:>2} "
                  f"{r['duration_s']:5.1f}s | {r['subject'][:24]}")
            return r

    return await asyncio.gather(*(guarded(x) for x in rows))


def _summary(items: list[dict]) -> dict:
    c = Counter(it["status"] for it in items)
    n = len(items)
    reached4 = n - c.get("err_stage3", 0)
    surv4 = c.get("survived", 0) + c.get("loss_stage5", 0)      # candidates>0
    reached5 = surv4
    surv5 = c.get("survived", 0)
    return {
        "n_claims": n,
        "status_counts": dict(c),
        "stage3_err": c.get("err_stage3", 0),
        "reached_stage4": reached4,
        "stage4_loss_no_candidates": c.get("loss_stage4", 0),
        "stage4_err": c.get("err_stage4", 0),
        "stage4_survivors_with_candidates": surv4,
        "reached_stage5": reached5,
        "stage5_loss_no_cell": c.get("loss_stage5", 0),
        "stage5_err": c.get("err_stage5", 0),
        "final_survivors_with_evidence": surv5,
        "stage4_survival_rate": round(surv4 / reached4, 3) if reached4 else None,
        "stage5_survival_rate": round(surv5 / reached5, 3) if reached5 else None,
        "end_to_end_survival_rate": round(surv5 / n, 3) if n else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()

    rows = _read(DATA, args.limit)
    print(f"claims={len(rows)}  concurrency={args.concurrency}  data={DATA.name}\n")
    t0 = time.perf_counter()
    items = asyncio.run(_run_all(rows, args.concurrency))
    wall = round(time.perf_counter() - t0, 1)
    items.sort(key=lambda r: (r["source_id"] or 0, r["claim_id"] or ""))

    summary = _summary(items)
    summary["wall_s"] = wall
    RESULT_JSON.write_text(
        json.dumps({"summary": summary, "items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    s = summary
    print("\n===== 3~5단계 퍼널 =====")
    print(f"진입 claim                 : {s['n_claims']}")
    print(f"  [3] normalize raise      : {s['stage3_err']}")
    print(f"[4] 진입                   : {s['reached_stage4']}")
    print(f"  [4] 손실(후보 0)          : {s['stage4_loss_no_candidates']}  (+raise {s['stage4_err']})")
    print(f"  [4] 생존(후보≥1)          : {s['stage4_survivors_with_candidates']}  rate={s['stage4_survival_rate']}")
    print(f"[5] 진입                   : {s['reached_stage5']}")
    print(f"  [5] 손실(셀 0)            : {s['stage5_loss_no_cell']}  (+raise {s['stage5_err']})")
    print(f"  최종 생존(evidence≥1)     : {s['final_survivors_with_evidence']}  rate={s['stage5_survival_rate']}")
    print(f"E2E 생존율                 : {s['end_to_end_survival_rate']}  (wall {wall}s)")


if __name__ == "__main__":
    main()
