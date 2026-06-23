"""[6] rank_evidence frozen-독립 평가 — Top-1 accuracy.

격리: 독립 입력(claim + 후보 표 evidences)을 직접 주입 → rank_evidence 실제 실행 →
1위(evidences[0])가 gold_best_index 표인지 채점. 캡처가 아니라 6_source_1(독립,
gold_best_index=병인님/원천소스 파생)이라 비순환·stale 무관.
실행: uv run x python benchmark/eval_stage6_frozen.py [--limit N]
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from benchmark.reporting import blank_sections, save_result
from benchmark.scoring import score_rank
from src.modules.rank_evidence import rank_evidence
from src.observability import set_eval_context
from src.schemas.runtime import (
    CellAttempt, Claim, ClaimAnalysis, ClaimType, Evidence, KosisQuery, KosisSearch,
    MasterSchema, ValueSlot,
)

SRC = Path("benchmark/data/6_rank/6_source_1.jsonl")
_DUMMY_SEARCH = dict(api="", query="", params="", hits=0, success=1, duration_ms=0)
_DUMMY_QUERY = dict(api="", tbl_id="", params="", rows_returned=0, success=1, duration_ms=0)


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def _period(p: str):
    """'M:2025-07' → (period_type, value)."""
    if ":" in (p or ""):
        pt, v = p.split(":", 1)
        return (pt if pt in ("Y", "M", "Q", "S", "D") else "Y"), v
    return "Y", (p or "")


def build_ms(rec):
    c = rec["claim"]
    cid = rec["claim_id"]
    pt, pv = _period(c.get("period", ""))
    claim = Claim(
        claim_id=cid, article_id=str(rec["row_id"]), sentence="",
        claim_type=ClaimType.ABSOLUTE, subject=c.get("subject", ""),
        value=ValueSlot(raw="", llm_value="", is_inferred=False),
        unit=c.get("unit", ""), aggregation="값", period_type=pt,
        period_value=ValueSlot(raw="", llm_value=pv, is_inferred=False),
        population=c.get("population", ""), cited_source="",
    )
    # 후보 표 → Evidence(원본 index 를 evidence_id 로 태깅) + CellAttempt(분류축 라벨용)
    evs, attempts = [], []
    for i, e in enumerate(rec["evidences"]):
        evs.append(Evidence(
            claim_id=cid, evidence_id=str(i), source="KOSIS", subject=c.get("subject", ""),
            unit=c.get("unit", ""), period_type=pt, period=pv, population=c.get("population", ""),
            value=e.get("value"), table_name=e.get("table_name"), kosis_tbl_id=e.get("tbl_id"),
        ))
        attempts.append(CellAttempt(
            tbl_id=e.get("tbl_id", ""), tbl_nm=e.get("table_name", ""),
            axes={ax: [] for ax in (e.get("axes") or [])},
        ))
    analysis = ClaimAnalysis(
        claim_id=cid, kosis_search=KosisSearch(**_DUMMY_SEARCH),
        kosis_query=KosisQuery(**_DUMMY_QUERY), evidences=evs, cell_attempts=attempts,
    )
    return MasterSchema(claims=[claim], analysis=[analysis])


async def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    set_eval_context(session_id="stage6-rank-frozen", tags=["bench", "stage6", "frozen"],
                     trace_name="eval:stage6:rank", environment="benchmark")
    rows = [r for r in load(SRC) if r.get("scorable") and r.get("gold_best_index") is not None]
    if limit:
        rows = rows[:limit]
    sem = asyncio.Semaphore(5)
    records = []

    async def one(rec):
        async with sem:
            ms = build_ms(rec)
            await rank_evidence(ms)
            ranked = ms.analysis[0].evidences
            won = int(ranked[0].evidence_id)          # 1위가 된 원본 index
            gold = rec["gold_best_index"]
            ev_in = [{"index": i, "tbl_id": e.get("tbl_id"), "table_name": e.get("table_name")}
                     for i, e in enumerate(rec["evidences"])]
            records.append({
                "row_id": rec["row_id"], "stage": 6, "claim_id": rec["claim_id"], "label": rec.get("label"),
                # input/output 슬라이스 = analysis (STAGE_IO[6] 계약): 받은 후보 표 / 재정렬 결과
                "input": {"analysis": [{"claim_id": rec["claim_id"], "evidences": ev_in}]},
                "output": {"analysis": [{"claim_id": rec["claim_id"], "top1_original_index": won,
                                         "reranked_order": [int(e.evidence_id) for e in ranked]}]},
                "gold_best_index": gold,              # 정답 라벨(input 아님) — 채점 기준(flat gold_*)
                "top1_correct": won == gold,
                "baseline_top1_correct": gold == 0,   # RANK 베이스라인 = 재정렬 전 0번
            })

    await asyncio.gather(*[one(r) for r in rows])
    records.sort(key=lambda r: r["row_id"])

    metrics = score_rank(records)
    sec = blank_sections()
    sec["개요"] = "6단계 rank_evidence **frozen-독립** 평가 — 후보 표 중 1위 선정 Top-1 accuracy."
    sec["테스트 방법"] = ("격리: 6_source_1(독립, gold_best_index) 의 claim·evidences 로 MasterSchema 구성 → "
                     "rank_evidence 실행 → evidences[0] 의 원본 index==gold_best_index=top1_correct. "
                     "베이스라인=RANK 순(index 0). 캡처 아님 → stale·순환 무관.")
    sec["분석"] = "Top-1 = 주제적합 표를 1위로 올린 비율. Δ vs RANK = LLM 재정렬이 원순서 대비 얼마나 개선했나."
    sec["한계·주의"] = ("기권(LLM null)은 모듈이 순서 유지로 흡수 → 기권율 미집계(0). "
                    "scorable=gold_best_index 존재 행만. rank_evidence 는 값 미사용(주제 적합도만).")
    j, d = save_result(6, "leeaain", records, metrics, sec)
    print(f"[stage 6 frozen-독립] records={len(records)} → {j.name}")
    for m in metrics:
        print(f"   {m['지표']} {m['값']} {m.get('95% CI','')}")


if __name__ == "__main__":
    asyncio.run(main())
