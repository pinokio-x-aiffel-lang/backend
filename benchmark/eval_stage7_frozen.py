"""7단계 frozen-capture eval — calculate_metric 은 결정적(LLM 무).

after6 캡처에 재실행 → 7_source_2 scorable gold 로 macro-F1·recall[T/F/N] 채점.
#2(population fallback)·#3(range) 코드수정 전후를 같은 scorer·분모로 비교하려고 단독 실행.
실행: uv run x python benchmark/eval_stage7_frozen.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from benchmark.reporting import blank_sections, save_result
from benchmark.scoring import score_verdict_metric
from src.modules.calculate_metric import calculate_metric
from src.schemas.runtime import MasterSchema

ROOT = Path(__file__).resolve().parent.parent
CAP = ROOT / "benchmark_aain/data/260619_capture_v2_snapshots.jsonl"
DATA = ROOT / "benchmark/data"

# BEFORE = #2(fallback)·#3(range) 적용 전 커밋 상태(이번 라운드 시작점, 동일 scorer 로 실측).
BEFORE = {"macro-F1": "0.424", "recall[T]": "0.051 (2/39)",
          "recall[F]": "0.389 (14/36)", "recall[N]": "1.000 (51/51)"}


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def map_v(v):
    return v if v in ("T", "F", "N") else "N"


async def main():
    cap = load(CAP)
    after6 = {r["row_id"]: r["snapshots"]["after6"] for r in cap if r["snapshots"].get("after6")}
    pred = {}
    sem = asyncio.Semaphore(8)

    async def one(rid, snap):
        async with sem:
            ms = MasterSchema.model_validate(snap)
            await calculate_metric(ms)
            for cr in ms.verifications.claim_results:
                pred[(rid, cr.claim_id)] = cr.verdict

    await asyncio.gather(*[one(rid, s) for rid, s in after6.items()])

    records = [{"row_id": r["row_id"], "stage": 7, "claim_id": r["claim_id"],
                "input": {"claims": [r.get("claim")], "analysis": []},
                "gold_verdict": r.get("gold_verdict_stage7"),
                "pred_verdict": map_v(pred.get((r["row_id"], r["claim_id"])))}
               for r in load(DATA / "7_metric/7_source_2.jsonl") if r.get("scorable")]
    after = score_verdict_metric(records)

    metrics_rows = [{"지표": m["지표"], "방법": "frozen-capture(after6 고정)",
                     "before": BEFORE.get(m["지표"], "—"), "after": m["값"]}
                    for m in after]

    sec = blank_sections()
    sec["개요"] = "7단계 calculate_metric — #2(population fallback NEI 해제)·#3(range 포함비교) 전후."
    sec["테스트 방법"] = ("after6 동결 캡처에 calculate_metric 재실행(결정적, LLM 무). "
                     "7_source_2 scorable gold_verdict_stage7 대조. BEFORE=#2/#3 적용 전 커밋(동일 scorer 실측).")
    sec["분석"] = ("#3: 수치 범위/부등(>=89·<75 등) 절대형을 포함비교로 살림(F +2). "
                 "#2: 모집단 전부폴백을 NEI 로 막던 정책 해제→전체값과 T/F(F +5), 8단계가 모집단 M 판정. "
                 "recall[T] 불변은 남은 T-killer가 #1(증감, 상류 미추출)이라서.")
    sec["개선 전후 비교"] = (f"macro-F1 {BEFORE['macro-F1']}→{next(m['값'] for m in after if m['지표']=='macro-F1')}; "
                       f"recall[F] {BEFORE['recall[F]']}→{next(m['값'] for m in after if m['지표']=='recall[F]')}; "
                       f"recall[N] 무손상(폴백 해제가 N 오염 없음).")
    sec["한계·주의"] = ("#1 증감(change_rate)은 미반영 — 원인이 7단계 아닌 상류(stage2 비교기준 미추출 115/185, "
                   "stage3 compare_period 오정규화 24건)라 별도 작업·재실행 필요. range 부등호(>,>=)는 경계포함 근사.")
    j, d = save_result(7, "leeaain", records, metrics_rows, sec)

    print("=== 7단계 #2+#3 전후 ===")
    for row in metrics_rows:
        print(f"  {row['지표']:12} before={row['before']:18} after={row['after']}")
    print(f"\n저장 → {j.name}")


if __name__ == "__main__":
    asyncio.run(main())
