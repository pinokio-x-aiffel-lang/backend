"""revert A/B용 캡처 생성 — f4d9ef9 캡처의 after6(고정 상류)에 현재 코드(HEAD)로 7→9 재실행.

목적: f4d9ef9(compare.py population-fallback F→NEI 강등) revert 효과를 노이즈 없이 측정.
상류 2~6단계는 f4d9ef9 캡처로 동결 → 변경은 오직 compare.py(stage7). 같은 after6 입력에
현재(revert) calculate_metric→check_alignment→decide_verdict 재실행해 after7/after9 만 교체.

출력: 같은 캡처 스키마(after2/4/5/6 보존 + after7/after9 갱신) →
      benchmark_aain/data/260624_capture_v2_revert.jsonl
이후: uv run x python benchmark_aain/eval_e2e_full.py benchmark_aain/data/260624_capture_v2_revert.jsonl

실행: uv run x python benchmark_aain/rerun_revert_capture_7to9.py
"""
from __future__ import annotations

import asyncio
import collections
import copy
import json
from pathlib import Path

from src.modules.calculate_metric import calculate_metric
from src.modules.check_alignment import check_alignment
from src.modules.decide_verdict import decide_verdict
from src.observability import set_eval_context
from src.schemas.runtime import MasterSchema

ROOT = Path(__file__).resolve().parent.parent
CAP = ROOT / "benchmark_aain/data/260624_capture_v2_f4d9ef9.jsonl"
OUT = ROOT / "benchmark_aain/data/260624_capture_v2_revert.jsonl"


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


async def main():
    set_eval_context(session_id="revert-7to9-AB", tags=["bench", "e2e", "revert", "7to9"],
                     trace_name="eval:revert:7to9", environment="benchmark")
    cap = load(CAP)
    sem = asyncio.Semaphore(5)
    done = 0
    n = len(cap)

    async def one(row):
        nonlocal done
        new = copy.deepcopy(row)
        snap = (row.get("snapshots") or {}).get("after6")
        if not row.get("failed_step") and snap:
            async with sem:
                ms = MasterSchema.model_validate(snap)
                await calculate_metric(ms)        # [7] revert된 compare.py
                new["snapshots"]["after7"] = copy.deepcopy(ms.model_dump(mode="json"))
                await check_alignment(ms)         # [8]
                await decide_verdict(ms)          # [9]
                new["snapshots"]["after9"] = copy.deepcopy(ms.model_dump(mode="json"))
        done += 1
        print(f"  [{done}/{n}] row{row['row_id']} {row.get('label')}", flush=True)
        return new

    results = await asyncio.gather(*[one(r) for r in cap])
    results.sort(key=lambda r: r["row_id"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for rec in results:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    dist = collections.Counter()
    for r in results:
        for cr in ((r["snapshots"].get("after9", {}).get("verifications") or {}).get("claim_results") or []):
            dist[cr.get("verdict")] += 1
    print(f"\nrevert 캡처 {len(results)}행 → {OUT}")
    print("after9 verdict 분포(revert):", dict(dist))


if __name__ == "__main__":
    asyncio.run(main())
