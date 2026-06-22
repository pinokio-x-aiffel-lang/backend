"""e2e 8단계 개선 전후(A/B) — after6 캡처(동결 상류)에 7→8→9 재실행.

BEFORE = 260619 캡처의 after7(metric)·after9(final) verdict (개선 전 코드).
AFTER  = 같은 after6 입력에 현재 코드로 calculate_metric→check_alignment→decide_verdict 재실행.
동일 gold(7_source_2 gold_verdict_stage7 · 8_source_2 gold.is_M)·동일 scorer·동일 scorable 분모로
채점하고 pred 만 교체 → 8단계 수정 귀속이 가능한 공정 A/B.

상류(2~6단계)는 after6 캡처로 동결되어 8단계 수정과 무관 → 재측정 안 함(불변).
저장: benchmark/e2e/ .  실행: uv run x python benchmark/eval_e2e_7to9_AB.py
"""
from __future__ import annotations

import asyncio
import collections
import json
from pathlib import Path

from benchmark.reporting import save_result, blank_sections
from benchmark.scoring import score_verdict_metric, score_alignment
from src.modules.calculate_metric import calculate_metric
from src.modules.check_alignment import check_alignment
from src.modules.decide_verdict import decide_verdict
from src.observability import set_eval_context
from src.schemas.runtime import MasterSchema

ROOT = Path(__file__).resolve().parent.parent
CAP = ROOT / "benchmark_aain/data/260619_capture_v2_snapshots.jsonl"
DATA = ROOT / "benchmark/data"


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def map_v(v):
    """stage7 라벨 공간(T/F/N)으로 사상. M·UNVERIFIED·None → N."""
    return v if v in ("T", "F", "N") else "N"


async def main():
    set_eval_context(session_id="e2e-stage8-AB", tags=["bench", "e2e", "stage8", "AB"],
                     trace_name="eval:e2e:stage8-AB", environment="benchmark")
    cap = load(CAP)

    # 캡처(개선 전) verdict 인덱스: (row_id, claim_id) → verdict
    before_cr7, before_cr9 = {}, {}
    after6_by_row = {}
    for r in cap:
        rid, s = r["row_id"], r["snapshots"]
        if s.get("after6"):
            after6_by_row[rid] = s["after6"]
        for cr in ((s.get("after7", {}).get("verifications") or {}).get("claim_results") or []):
            before_cr7[(rid, cr["claim_id"])] = cr.get("verdict")
        for cr in ((s.get("after9", {}).get("verifications") or {}).get("claim_results") or []):
            before_cr9[(rid, cr["claim_id"])] = cr.get("verdict")

    # ── 현재 코드로 7→8→9 재실행 → after7/after9 verdict 캡처 ──
    after_cr7, after_cr9 = {}, {}
    sem = asyncio.Semaphore(5)

    async def one(rid, snap):
        async with sem:
            ms = MasterSchema.model_validate(snap)
            await calculate_metric(ms)        # [7] cr.verdict 를 T/F/N 으로 시드
            for cr in ms.verifications.claim_results:
                after_cr7[(rid, cr.claim_id)] = cr.verdict
            await check_alignment(ms)         # [8] T→M 보정
            await decide_verdict(ms)          # [9] 최종 확정
            for cr in ms.verifications.claim_results:
                after_cr9[(rid, cr.claim_id)] = cr.verdict

    await asyncio.gather(*[one(rid, snap) for rid, snap in after6_by_row.items()])

    # ── 채점: 동일 gold·scorer, pred 만 before/after 교체 ──
    def score_stage7(cr7):
        recs = []
        for r in load(DATA / "7_metric/7_source_2.jsonl"):
            if not r.get("scorable"):
                continue
            key = (r["row_id"], r["claim_id"])
            recs.append({"gold_verdict": r.get("gold_verdict_stage7"),
                         "pred_verdict": map_v(cr7.get(key))})
        return recs, score_verdict_metric(recs)

    def score_stage8(cr9):
        recs = []
        for r in load(DATA / "8_alignment/8_source_2.jsonl"):
            if not r.get("scorable"):
                continue
            key = (r["row_id"], r["claim_id"])
            recs.append({"gold_M": bool((r.get("gold") or {}).get("is_M")),
                         "pred_M": cr9.get(key) == "M"})
        return recs, score_alignment(recs)

    b7_recs, b7 = score_stage7(before_cr7)
    a7_recs, a7 = score_stage7(after_cr7)
    b8_recs, b8 = score_stage8(before_cr9)
    a8_recs, a8 = score_stage8(after_cr9)

    # before/after 결합표(단계·지표·방법·before·after) → e2e md '성능 수치'
    def val(rows, name):
        for m in rows:
            if m["지표"] == name:
                return m["값"]
        return "—"

    metrics_rows = []
    for name in ["macro-F1", "recall[T]", "recall[F]", "recall[N]"]:
        metrics_rows.append({"단계": "7 metric", "지표": name, "방법": "cascade(재실행)",
                             "before": val(b7, name), "after": val(a7, name)})
    for name in ["M-recall", "M-precision", "M-F1", "NEI(LLM 실패)율"]:
        metrics_rows.append({"단계": "8 alignment", "지표": name, "방법": "cascade(재실행)",
                             "before": val(b8, name), "after": val(a8, name)})

    # 저장용 records: 8단계 A/B pred (재실행 결과) 보존
    save_recs = [{"row_id": r["row_id"], "stage": 8, "claim_id": r["claim_id"],
                  "gold_M": bool((r.get("gold") or {}).get("is_M")),
                  "before_pred": before_cr9.get((r["row_id"], r["claim_id"])),
                  "after_pred": after_cr9.get((r["row_id"], r["claim_id"]))}
                 for r in load(DATA / "8_alignment/8_source_2.jsonl") if r.get("scorable")]

    sec = blank_sections()
    sec["개요"] = "8단계(check_alignment) 개선 전후 e2e A/B — after6 동결 입력에 7→8→9 재실행."
    sec["테스트 방법"] = ("BEFORE=260619 캡처 after7/after9 verdict(개선 전). "
                     "AFTER=같은 after6 입력에 현재 코드 재실행. 동일 v2 gold·scorer·scorable 분모, pred만 교체.")
    sec["분석"] = (f"M행 최종 verdict 분포(after)는 print 참조. compare.py 빈단위→가정비교 + "
                 f"8단계 framing 탐지 프롬프트로 M-recall {val(b8,'M-recall')} → {val(a8,'M-recall')}.")
    sec["개선 전후 비교"] = (f"stage7 macro-F1 {val(b7,'macro-F1')}→{val(a7,'macro-F1')}; "
                       f"stage8 M-recall {val(b8,'M-recall')}→{val(a8,'M-recall')}, "
                       f"M-F1 {val(b8,'M-F1')}→{val(a8,'M-F1')}. 상류 2~6은 동결(불변).")
    sec["한계·주의"] = ("cascade: 상류 5단계 셀-매칭 오류가 그대로 분모에 남아 M-recall 상한을 누른다. "
                   "모듈 자체 실력은 격리평가(8_alignment, M-recall 0.967) 참조.")

    j, d = save_result("e2e", "leeaain", save_recs, metrics_rows, sec)

    print("=== before(캡처) / after(재실행) ===")
    print(f"after7 분포: {dict(collections.Counter(after_cr7.values()))}")
    print(f"after9 분포: {dict(collections.Counter(after_cr9.values()))}")
    for row in metrics_rows:
        print(f"  [{row['단계']}] {row['지표']:16} before={row['before']:24} after={row['after']}")
    print(f"\n저장 → {j}\n      {d}")


if __name__ == "__main__":
    asyncio.run(main())
