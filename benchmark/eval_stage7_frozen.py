"""[7] calculate_metric frozen-독립 평가 — macro-F1 + recall[T/F/N].

격리: 독립 입력만 조립해 그 모듈만 실행(캡처 아님 → stale·순환 무관).
  claim_value = 7_source_1(value_llm, gold_verdict_stage7)  [독립]
  official_value = 5_source_1.gold.value (SSOT figure)       [독립]
둘을 row_id 로 조인 → claim + evidence(공식값) MasterSchema → calculate_metric →
verdict 를 gold_verdict_stage7 로 채점. 무증거(N) 행은 evidence 없이 주입.
calculate_metric 은 결정적(LLM 무).
실행: uv run x python benchmark/eval_stage7_frozen.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from benchmark.reporting import blank_sections, save_result
from benchmark.scoring import score_verdict_metric
from src.modules.calculate_metric import calculate_metric
from src.schemas.runtime import (
    Claim, ClaimAnalysis, ClaimType, Evidence, KosisQuery, KosisSearch,
    MasterSchema, ValueSlot, Verifications, VerificationSummary,
)

S7 = Path("benchmark/data/7_metric/7_source_1.jsonl")
S5 = Path("benchmark/data/5_fetch/5_source_1.jsonl")
_DUMMY_SEARCH = dict(api="", query="", params="", hits=0, success=1, duration_ms=0)
_DUMMY_QUERY = dict(api="", tbl_id="", params="", rows_returned=0, success=1, duration_ms=0)


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def map_v(v):
    v = v.value if hasattr(v, "value") else v
    return v if v in ("T", "F", "N") else "N"


def _ctype(s):
    try:
        return ClaimType(s)
    except ValueError:
        return ClaimType.ABSOLUTE


def build_ms(row, official):
    c = row["claim"]
    cid = row.get("claim_id", "clm-0001")
    pt = c.get("claim_type")
    claim = Claim(
        claim_id=cid, article_id=str(row["row_id"]), sentence="",
        claim_type=_ctype(c.get("claim_type")), subject="",
        value=ValueSlot(raw="", llm_value=str(c.get("value_llm", "")), is_inferred=False),
        unit=c.get("unit", ""), aggregation="값", period_type="Y",
        period_value=ValueSlot(raw="", llm_value=str(c.get("period_llm", "")), is_inferred=False),
        population="", cited_source="",
    )
    evs = []
    if official is not None:
        evs = [Evidence(
            claim_id=cid, source="KOSIS", subject="", unit=str(official.get("unit", "")),
            period_type="Y", period="", population="", value=official.get("value"),
            table_name="(official)",
        )]
    analysis = ClaimAnalysis(claim_id=cid, kosis_search=KosisSearch(**_DUMMY_SEARCH),
                             kosis_query=KosisQuery(**_DUMMY_QUERY), evidences=evs)
    return MasterSchema(claims=[claim], analysis=[analysis],
                        verifications=Verifications(summary=VerificationSummary(total_claims=1)))


async def main():
    s7 = [r for r in load(S7) if r.get("scorable") and r.get("claim")]
    g5 = {(r["row_id"], r.get("claim_id")): (r.get("gold") or {}) for r in load(S5)}
    sem = asyncio.Semaphore(8)
    records = []

    async def one(row):
        async with sem:
            gold = g5.get((row["row_id"], row.get("claim_id")), {})
            official = gold if gold.get("value") is not None else None
            ms = build_ms(row, official)
            await calculate_metric(ms)
            pred = map_v(ms.verifications.claim_results[0].verdict)
            records.append({
                "row_id": row["row_id"], "stage": 7, "claim_id": row.get("claim_id"),
                "label": row.get("label"),
                "input": {"claims": [row["claim"]],
                          "analysis": [{"evidences": [{"value": (official or {}).get("value"),
                                                       "unit": (official or {}).get("unit")}] if official else []}]},
                "output": {"verifications": {"claim_results": [{"claim_id": row.get("claim_id"),
                                                                "verdict": pred}]}},
                "gold_verdict": map_v(row.get("gold_verdict_stage7")),
                "pred_verdict": pred,
            })

    await asyncio.gather(*[one(r) for r in s7])
    records.sort(key=lambda r: r["row_id"])

    metrics = score_verdict_metric(records)
    sec = blank_sections()
    sec["개요"] = "7단계 calculate_metric **frozen-독립** 평가 — macro-F1 + recall[T/F/N]."
    sec["테스트 방법"] = ("격리: 독립 claim_value(7_source_1) + 독립 official figure(5_source_1.gold)를 "
                     "row_id 조인 → claim+evidence MasterSchema → calculate_metric(결정적) → "
                     "verdict 를 gold_verdict_stage7 대조. 무증거(N)는 evidence 없이 주입. 캡처 아님.")
    sec["분석"] = "캡처 입력(stale) 대체: 공식값을 SSOT figure 로 고정해 상류와 무관하게 비교 로직만 측정."
    sec["한계·주의"] = ("official 값이 SSOT figure 로 존재하는 행만(주로 T/F). N 은 무증거로 표현. "
                    "단위 환산은 calculate_metric 내부 규칙에 의존.")
    j, d = save_result(7, "leeaain", records, metrics, sec)
    print(f"[stage 7 frozen-독립] records={len(records)} → {j.name}")
    for m in metrics:
        print(f"   {m['지표']} {m['값']} {m.get('95% CI','')}")


if __name__ == "__main__":
    asyncio.run(main())
