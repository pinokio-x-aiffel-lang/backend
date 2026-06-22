"""[8] check_alignment 격리 평가 — M-recall/precision 실측.

격리: verdict=T(수치 일치) + 올바른 증거 + 왜곡 문장을 직접 주입 → alignment 실제 실행.
  pred_M = 재판정 verdict==M / gold_M = label==M(병인님 왜곡기법 존재).
cascade(0.0)와 달리 8단계 자체 실력(왜곡을 M으로 잡나)을 측정.
입력: benchmark/data/8_alignment/8_source_3.jsonl (원천소스 추출, 비순환).
실행: uv run x python benchmark/eval_stage8.py [--limit N]
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from benchmark.reporting import save_result, blank_sections
from benchmark.scoring import score_alignment
from src.modules.check_alignment import check_alignment
from src.observability import set_eval_context
from src.schemas.runtime import (
    Article, Claim, ClaimAnalysis, ClaimResult, ClaimType, Evidence, KosisQuery, KosisSearch,
    MasterSchema, MetricResult, PeriodType, ValueSlot, Verdict, Verifications, VerificationSummary,
)

SRC = Path("benchmark/data/8_alignment/8_source_3.jsonl")
_DUMMY_SEARCH = dict(api="", query="", params="", hits=0, success=1, duration_ms=0)
_DUMMY_QUERY = dict(api="", tbl_id="", params="", rows_returned=0, success=1, duration_ms=0)


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def build_ms(rec):
    c, e = rec["claim"], rec["evidence"]
    cid = rec["claim_id"]
    claim = Claim(
        claim_id=cid, article_id=str(rec["row_id"]), sentence=c.get("sentence", ""),
        claim_type=ClaimType.ABSOLUTE, subject=c.get("subject", ""),
        value=ValueSlot(raw="", llm_value=str(e.get("value", "")), is_inferred=False),
        unit=c.get("unit", ""), aggregation=c.get("aggregation", "값"),
        period_type="Y", period_value=ValueSlot(raw="", llm_value=str(c.get("period_llm", "")), is_inferred=False),
        population=c.get("population", ""), cited_source="",
    )
    ev = Evidence(
        claim_id=cid, source="KOSIS", subject=e.get("subject", ""), unit=e.get("unit", ""),
        period_type="Y", period=str(e.get("period", "")), population=e.get("population", ""),
        value=e.get("value"), table_name=e.get("table_name"), population_fallback=bool(e.get("population_fallback")),
    )
    analysis = ClaimAnalysis(claim_id=cid, kosis_search=KosisSearch(**_DUMMY_SEARCH),
                             kosis_query=KosisQuery(**_DUMMY_QUERY), evidences=[ev])
    cr = ClaimResult(claim_id=cid, claim_value=str(e.get("value", "")), kosis_value=str(e.get("value", "")),
                     metric=MetricResult(operation="absolute", verdict=Verdict.TRUE,
                                         claim_value=float(e["value"]) if e.get("value") is not None else None,
                                         kosis_value=float(e["value"]) if e.get("value") is not None else None,
                                         within_tolerance=True))
    # A-vs-B용 원문: 8_source_3 는 claim.sentence 에 원문 전체를 담고 있음 → article 로도 제공.
    article = Article(article_id=str(rec["row_id"]), content=c.get("sentence", ""))
    return MasterSchema(article=article, claims=[claim], analysis=[analysis],
                        verifications=Verifications(summary=VerificationSummary(total_claims=1), claim_results=[cr]))


async def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    # Langfuse 분리: environment=benchmark(통째 분리) + session/tags/name(이 실험만 식별)
    set_eval_context(session_id="stage8-align-AB", tags=["bench", "stage8", "align-AB"],
                     trace_name="eval:stage8:align", environment="benchmark")
    rows = load(SRC)
    if limit:
        rows = rows[:limit]
    sem = asyncio.Semaphore(5)
    records = []

    async def one(rec):
        async with sem:
            ms = build_ms(rec)
            await check_alignment(ms)
            metric = ms.verifications.claim_results[0].metric
            v = metric.verdict
            vstr = v.value if hasattr(v, "value") else v
            mt = metric.mismatch_type
            pred_dim = mt.value if hasattr(mt, "value") else mt
            gold_M = (rec.get("gold") or {}).get("aligned") is False
            records.append({
                "row_id": rec["row_id"], "stage": 8, "label": rec.get("label"),
                "input": {"verifications": {"claim_results": [{"claim_id": rec["claim_id"], "verdict": "T"}]}},
                "output": {"verdict_after": vstr, "pred_dimension": pred_dim,
                           "align_reason": metric.align_reason},
                "gold_M": gold_M, "pred_M": vstr == "M", "nei": vstr == "N",
                "gold_dimension": (rec.get("gold") or {}).get("dimension"),
            })

    await asyncio.gather(*[one(r) for r in rows])

    metrics = score_alignment(records)
    sec = blank_sections()
    sec["개요"] = "8단계 check_alignment **격리** 평가 — verdict=T+올바른 증거+왜곡문장 주입해 M-recall/precision 실측."
    sec["테스트 방법"] = ("격리: 8_source_3(원천소스 추출)의 claim·evidence로 MasterSchema 구성, "
                     "metric.verdict=T 주입 → check_alignment 실행 → 재판정 verdict==M=pred_M. "
                     "gold_M=label==M(병인님 왜곡). cascade(M-recall 0.0)와 달리 모듈 실제 실행.")
    sec["분석"] = "이 수치가 8단계 프롬프트의 진짜 왜곡탐지 실력. M-recall=왜곡을 M으로 잡은 비율, M-precision=M판정 중 진짜 M."
    sec["개선 전후 비교"] = "cascade(M-recall 0.0, 미실행) → 격리(실측). 0.0은 '상류 막힘'이지 모듈 실력 아니었음을 보임."
    sec["한계·주의"] = ("claim 슬롯(subject/unit/pop)은 병인님·원문 규칙파싱(근사). NEI=LLM 판정실패. "
                    "격리는 '올바른 입력 가정' 실력이며, 실운영은 상류가 T를 만들어줘야 발동.")
    j, d = save_result(8, "leeaain", records, metrics, sec)
    import collections
    print(f"[stage 8 격리] records={len(records)} → {j.name}")
    print("  verdict 분포:", dict(collections.Counter(r["output"]["verdict_after"] for r in records)))
    for m in metrics:
        print(f"   {m['지표']} {m['값']} {m.get('95% CI','')}")


if __name__ == "__main__":
    asyncio.run(main())
