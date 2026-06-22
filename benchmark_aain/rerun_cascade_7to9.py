"""7단계 단위가드 수정 효과 검증 — 캡처 after6(랭킹 後)에서 7→8→9 재실행.

수정 전: M행 verdict T=0(빈 단위→NEI) → [8] 미발동(M-recall 0.0 cascade).
이 스크립트: 같은 입력(after6)에 수정된 calculate_metric→check_alignment→decide_verdict 재실행
→ M행이 T→M으로 흐르는지 + cascade stage-8 M-recall 측정.
실행: uv run x python benchmark_aain/rerun_cascade_7to9.py
"""
from __future__ import annotations

import asyncio
import collections
import json
from pathlib import Path

from benchmark.reporting import save_result, blank_sections
from benchmark.scoring import score_alignment
from src.modules.calculate_metric import calculate_metric
from src.modules.check_alignment import check_alignment
from src.modules.decide_verdict import decide_verdict
from src.observability import set_eval_context
from src.schemas.runtime import MasterSchema

ROOT = Path(__file__).resolve().parent.parent
CAP = ROOT / "benchmark_aain/data/260619_capture_v2_snapshots.jsonl"
SSOT = ROOT / "benchmark/data/ssot/260614_master_eval_213_parsed_human_checked_SSOT.jsonl"


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


async def main():
    set_eval_context(session_id="stage8-align-AB-cascade", tags=["bench", "stage8", "align-AB", "cascade"],
                     trace_name="eval:stage8:align-cascade", environment="benchmark")
    cap = load(CAP)
    label = {r["row_id"]: r["label"] for r in load(SSOT)}
    sem = asyncio.Semaphore(5)
    records = []
    mrow_verdicts = collections.Counter()

    async def one(row):
        if row.get("failed_step"):
            return
        snap = (row.get("snapshots") or {}).get("after6")
        if not snap:
            return
        async with sem:
            ms = MasterSchema.model_validate(snap)
            await calculate_metric(ms)      # 7 (수정됨)
            await check_alignment(ms)       # 8
            await decide_verdict(ms)        # 9
            lab = label.get(row["row_id"])
            for cr in ms.verifications.claim_results:
                v = cr.verdict
                if lab == "M":
                    mrow_verdicts[v] += 1
                # cascade stage-8 채점: gold_M=label==M, pred_M=verdict==M
                records.append({
                    "row_id": row["row_id"], "stage": 8, "label": lab,
                    "input": {"verifications": {"claim_results": [{"claim_id": cr.claim_id}]}},
                    "output": {"verdict": v},
                    "gold_M": lab == "M", "pred_M": v == "M", "nei": v == "N",
                })

    await asyncio.gather(*[one(r) for r in cap])

    metrics = score_alignment(records)
    sec = blank_sections()
    sec["개요"] = "7단계 단위가드 수정 후 cascade 재실행(7→8→9, after6 입력) — stage-8 M-recall 재측정."
    sec["테스트 방법"] = "캡처 after6(랭킹後)에 수정 calculate_metric→check_alignment→decide_verdict 재실행. gold_M=label==M, pred_M=최종 verdict==M."
    sec["분석"] = "수정 전 cascade M-recall 0.0(M행 T=0→[8] 미발동). 빈 단위→값비교 허용으로 M이 T→M 흐르는지 확인."
    sec["개선 전후 비교"] = "이전 cascade(eval_v2_from_capture) M-recall 0.0 ↔ 본 수정후 수치."
    sec["한계·주의"] = "여전히 cascade(상류 5단계 셀-매칭 오류 포함). 5단계 미수정분(오매칭9·미조회8)은 그대로 막힘."
    j, d = save_result(8, "leeaain", records, metrics, sec)
    print("=== M행 최종 verdict 분포 (수정 후) ===", dict(mrow_verdicts))
    print(f"전체 verdict 분포:", dict(collections.Counter(r["output"]["verdict"] for r in records)))
    print(f"\n[stage 8 cascade 재실행] records={len(records)} → {j.name}")
    for m in metrics:
        print(f"   {m['지표']} {m['값']} {m.get('95% CI','')}")


if __name__ == "__main__":
    asyncio.run(main())
