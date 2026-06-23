"""[5] fetch_kosis_data frozen-독립 평가 — coverage × 셀값 accuracy.

격리: 독립 입력(claim + 후보 표) 고정 주입 → fetch_kosis_data 실제 실행(라이브 KOSIS) →
가져온 셀값이 독립 gold(SSOT figure)와 일치하나 채점. 입력은 5_source_1(고정), gold 는
figure(독립) → 캡처 stale·순환 무관. fetch 는 외부 KOSIS 호출(frozen=입력만 고정).
실행: uv run x python benchmark/eval_stage5_frozen.py [--limit N]
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from benchmark.reporting import blank_sections, save_result
from benchmark.scoring import score_fetch
from src.modules.fetch_kosis_data import fetch_kosis_data
from src.schemas.runtime import (
    Claim, ClaimAnalysis, ClaimType, KosisCandidate, KosisQuery, KosisSearch,
    MasterSchema, ValueSlot,
)

SRC = Path("benchmark/data/5_fetch/5_source_1.jsonl")
_DUMMY_SEARCH = dict(api="", query="", params="", hits=0, success=1, duration_ms=0)
_DUMMY_QUERY = dict(api="", tbl_id="", params="", rows_returned=0, success=1, duration_ms=0)


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def _close(a, b, rel=0.01):
    if a is None or b is None:
        return False
    a, b = float(a), float(b)
    if b == 0:
        return abs(a) < 1e-9
    return abs(a - b) / abs(b) <= rel


def _cell_correct(evidences, gold_v):
    """gold figure 와 일치하는 셀이 하나라도 있나. 천명↔명 등 ×1000 단위차 허용."""
    for ev in evidences:
        v = ev.value
        if _close(v, gold_v) or _close(v, gold_v * 1000) or _close(v, gold_v / 1000):
            return True
    return False


def build_ms(rec):
    c = rec["claim"]
    cid = rec["claim_id"]
    pt = c.get("period_type", "Y")
    claim = Claim(
        claim_id=cid, article_id=str(rec["row_id"]), sentence="",
        claim_type=ClaimType.ABSOLUTE, subject=c.get("subject", ""),
        value=ValueSlot(raw="", llm_value="", is_inferred=False),
        unit=c.get("unit", ""), aggregation="값",
        period_type=pt if pt in ("Y", "M", "Q", "S", "D") else "Y",
        period_value=ValueSlot(raw="", llm_value=str(c.get("period_value_llm", "")), is_inferred=False),
        population=c.get("population", ""), cited_source="",
    )
    cands = [KosisCandidate(org_id=str(x.get("org_id", "")), tbl_id=str(x.get("tbl_id", "")),
                            tbl_nm=str(x.get("tbl_nm", ""))) for x in rec.get("candidates", [])]
    analysis = ClaimAnalysis(claim_id=cid, kosis_search=KosisSearch(**_DUMMY_SEARCH),
                             kosis_query=KosisQuery(**_DUMMY_QUERY), candidates=cands)
    return MasterSchema(claims=[claim], analysis=[analysis])


async def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    rows = [r for r in load(SRC)
            if r.get("scorable") and r.get("candidates") and (r.get("gold") or {}).get("value") is not None]
    if limit:
        rows = rows[:limit]
    sem = asyncio.Semaphore(4)
    records = []

    async def one(rec):
        async with sem:
            ms = build_ms(rec)
            try:
                await fetch_kosis_data(ms)
                evs = ms.analysis[0].evidences
            except Exception:
                evs = []
            answered = any(e.value is not None for e in evs)
            gold_v = rec["gold"]["value"]
            records.append({
                "row_id": rec["row_id"], "stage": 5, "claim_id": rec["claim_id"], "label": rec.get("label"),
                "input": {"claims": [rec["claim"]],
                          "analysis": [{"candidates": rec.get("candidates", [])}]},
                "output": {"analysis": [{"evidences": [{"value": e.value, "unit": e.unit,
                                                        "tbl": e.kosis_tbl_id} for e in evs]}]},
                "answered": answered,
                "cell_correct": bool(answered and _cell_correct(evs, gold_v)),
            })

    done = 0
    for fut in asyncio.as_completed([one(r) for r in rows]):
        await fut
        done += 1
        if done % 30 == 0:
            print(f"  {done}/{len(rows)}", flush=True)
    records.sort(key=lambda r: r["row_id"])

    metrics = score_fetch(records)
    sec = blank_sections()
    sec["개요"] = "5단계 fetch_kosis_data **frozen-독립** 평가 — coverage × 셀값 accuracy(조회분)."
    sec["테스트 방법"] = ("격리: 5_source_1(고정 claim+후보 표) → fetch_kosis_data(라이브 KOSIS) → "
                     "가져온 셀값이 독립 gold(SSOT figure)와 일치(rel 1%, 천명↔명 ×1000 허용)하나 채점. "
                     "frozen=입력 고정(캡처 아님), 모듈은 외부 KOSIS 호출.")
    sec["분석"] = "coverage=후보표에서 셀 조회 성공률, 셀값 accuracy=조회분 중 figure 일치율. 둘의 곱이 실효 정답셀."
    sec["한계·주의"] = ("입력 후보표는 고정셋(retrieve 품질 미포함 — 그건 4단계). gold=figure 존재 행만. "
                    "단위차는 ×1000 근사 허용이라 드문 동일배수 오탐 가능.")
    j, d = save_result(5, "leeaain", records, metrics, sec)
    print(f"[stage 5 frozen-독립] records={len(records)} → {j.name}")
    for m in metrics:
        print(f"   {m['지표']} {m['값']} {m.get('95% CI','')}")


if __name__ == "__main__":
    asyncio.run(main())
