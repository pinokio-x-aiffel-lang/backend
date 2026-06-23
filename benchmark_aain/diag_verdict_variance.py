"""verdict 노이즈 분리 실험 — 같은 코드·같은 상류(after6 동결)로 7→9단계만 N회 반복.

목적: run1↔run2 점수 차이가 (a) 코드 변경 때문인지 (b) 순수 LLM 비결정성인지 구분.
after6(=stage6 출력)을 한 캡처에서 동결 → calculate_metric→check_alignment→decide_verdict 를
N회 재실행 → 매번 stage7(macro-F1·recall[T/F/N])·stage8(M-recall) 채점 → 폭(min~max) 보고.
폭이 run1↔run2 차이를 덮으면 = 그 차이는 노이즈로 설명됨(코드 퇴보 증거 아님).

실행: uv run x python benchmark_aain/diag_verdict_variance.py [capture.jsonl] [N]
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from benchmark.scoring import score_alignment, score_verdict_metric
from src.modules.calculate_metric import calculate_metric
from src.modules.check_alignment import check_alignment
from src.modules.decide_verdict import decide_verdict
from src.observability import set_eval_context
from src.schemas.runtime import MasterSchema

ROOT = Path(__file__).resolve().parent.parent
CAP = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "benchmark_aain/data/260623_capture_v2_run2.jsonl"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 3
DATA = ROOT / "benchmark/data"


def load(p):
    return [json.loads(s) for ln in Path(p).read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def map_v(v):
    return v if v in ("T", "F", "N") else "N"


async def run_trial(after6_by_row, sem):
    """동결 after6 → 7→9 재실행 → (row,claim)→최종 verdict."""
    cr9 = {}

    async def one(rid, snap):
        async with sem:
            ms = MasterSchema.model_validate(snap)
            await calculate_metric(ms)
            await check_alignment(ms)
            await decide_verdict(ms)
            for cr in ms.verifications.claim_results:
                cr9[(rid, cr.claim_id)] = cr.verdict

    await asyncio.gather(*[one(rid, snap) for rid, snap in after6_by_row.items()])
    return cr9


def score(cr9):
    r7 = [{"gold_verdict": r.get("gold_verdict_stage7"),
           "pred_verdict": map_v(cr9.get((r["row_id"], r["claim_id"])))}
          for r in load(DATA / "7_metric/7_source_2.jsonl") if r.get("scorable")]
    r8 = [{"gold_M": bool((r.get("gold") or {}).get("is_M")),
           "pred_M": cr9.get((r["row_id"], r["claim_id"])) == "M"}
          for r in load(DATA / "8_alignment/8_source_2.jsonl") if r.get("scorable")]
    m7 = {m["지표"]: m["값"] for m in score_verdict_metric(r7)}
    m8 = {m["지표"]: m["값"] for m in score_alignment(r8)}
    return {"macro-F1": m7["macro-F1"], "recall[T]": m7["recall[T]"],
            "recall[F]": m7["recall[F]"], "M-recall": m8["M-recall"]}


async def main():
    set_eval_context(session_id="verdict-variance", tags=["bench", "diag", "variance"],
                     trace_name="diag:verdict-variance", environment="benchmark")
    cap = load(CAP)
    after6 = {r["row_id"]: r["snapshots"]["after6"]
              for r in cap if r["snapshots"].get("after6")}
    print(f"동결 after6: {len(after6)}행 | {N}회 반복 | 캡처={CAP.name}\n")
    sem = asyncio.Semaphore(5)

    results = []
    for t in range(1, N + 1):
        cr9 = await run_trial(after6, sem)
        s = score(cr9)
        results.append(s)
        print(f"[trial {t}] " + "  ".join(f"{k}={v}" for k, v in s.items()), flush=True)

    print("\n=== 폭(min ~ max) — 같은 코드·동결 상류에서의 순수 LLM 노이즈 ===")
    import re
    for key in ["macro-F1", "recall[T]", "recall[F]", "M-recall"]:
        vals = []
        for r in results:
            m = re.search(r"[\d.]+", str(r[key]))
            if m:
                vals.append(float(m.group()))
        if vals:
            print(f"  {key:12} {min(vals):.3f} ~ {max(vals):.3f}  (폭 {max(vals)-min(vals):.3f})")


if __name__ == "__main__":
    asyncio.run(main())
