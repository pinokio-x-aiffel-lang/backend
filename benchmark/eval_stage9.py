"""[9] decide_verdict 평가 — 집계 산식(verdict_counts·overall_confidence·coverage) 검증.

모듈 격리: 입력=시나리오 claim_results(고정), gold=기대 집계값(독립 산식). 결정적(오차 0 기대).
실행: uv run x python benchmark/eval_stage9.py
"""
from __future__ import annotations

import json
from pathlib import Path

from benchmark.reporting import save_result, blank_sections
from benchmark.scoring import score_decide_verdict
from src.modules.decide_verdict import decide_verdict
from src.schemas.runtime import (
    ClaimResult, MasterSchema, MetricResult, Verdict, Verifications, VerificationSummary,
)
import asyncio

SRC = Path("benchmark/data/9_verdict/9_source_1.jsonl")


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def _eq(a, b, tol=1e-6):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return a == b


async def main():
    rows = load(SRC)
    records = []
    for sc in rows:
        crs = []
        for i, c in enumerate(sc.get("claim_results") or []):
            v = c.get("verdict")
            crs.append(ClaimResult(claim_id=str(c.get("row_id", i)),
                                   metric=MetricResult(operation="", verdict=Verdict(v))))
        ms = MasterSchema(verifications=Verifications(
            summary=VerificationSummary(total_claims=len(crs)), claim_results=crs))
        await decide_verdict(ms)
        s = ms.verifications.summary
        got = {"verdict_counts": dict(s.verdict_counts),
               "overall_confidence": s.overall_confidence, "coverage": s.coverage}
        g = sc.get("gold") or {}
        match = (got["verdict_counts"] == g.get("verdict_counts")
                 and _eq(got["overall_confidence"], g.get("overall_confidence"))
                 and _eq(got["coverage"], g.get("coverage")))
        records.append({
            "row_id": sc.get("group_id"), "stage": 9, "scenario": sc.get("scenario"),
            "input": {"verifications": {"claim_results": sc.get("claim_results")}},
            "output": {"verifications": {"summary": got}},
            "gold": g, "match": bool(match),
        })

    metrics = score_decide_verdict(records)
    sec = blank_sections()
    sec["개요"] = "9단계 decide_verdict — 집계 산식(verdict_counts·overall_confidence=T/(T+F+M)·coverage=(T+F+M)/total) 검증."
    sec["테스트 방법"] = ("모듈 격리: 시나리오별 claim_results(고정 입력)→decide_verdict 실행→summary 산출, "
                     "독립 기대 산식과 exact-match. 데이터=benchmark/data/9_verdict/9_source_1.jsonl(11 시나리오).")
    sec["분석"] = "결정적 집계라 오차 0 기대. 불일치 시 산식 회귀(버그)."
    sec["한계·주의"] = "시나리오 11개(합성, 집계 검증용). 실데이터 분포가 아니라 산식 정확성 테스트."
    j, d = save_result(9, "leeaain", records, metrics, sec)
    n = sum(1 for r in records if r["match"])
    print(f"[stage 9] exact-match {n}/{len(records)} → {j.name}")
    for m in metrics:
        print(f"   {m['지표']} {m['값']} {m.get('95% CI','')}")
    # 불일치 시 진단
    for r in records:
        if not r["match"]:
            print(f"   ✗ {r['scenario']}: got={r['output']['verifications']['summary']} gold={r['gold']}")


if __name__ == "__main__":
    asyncio.run(main())
