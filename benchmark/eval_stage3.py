"""[3] normalize_claim 평가 — value·period·compare_period accuracy + 룰 커버리지.

모듈 격리: 입력=3_source(고정, value/period/compare raw + base), gold=독립(expected).
각 행을 _normalize_one(claim, base) 로 실제 정규화 → llm_value 를 gold 와 대조.
실행: uv run x python benchmark/eval_stage3.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from benchmark.reporting import blank_sections, save_result
from benchmark.scoring import score_normalize
from src.modules.normalize_claim import _normalize_one, _parse_value
from src.schemas.runtime import Claim, ClaimType, ValueSlot

SRCS = [Path("benchmark/data/3_normalize/3_source_1.jsonl"),
        Path("benchmark/data/3_normalize/3_source_2.jsonl")]
CONCURRENCY = 6


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


async def run_one(sem, row):
    async with sem:
        base = row.get("base") or ""
        v_raw = (row.get("value") or {}).get("raw", "") or ""
        p_raw = (row.get("period_value") or {}).get("raw", "") or ""
        c_raw = (row.get("compare_period_value") or {}).get("raw", "") or ""
        claim = Claim(
            claim_id=f"r{row['row_id']}", article_id="eval", sentence=row.get("src_text", ""),
            claim_type=ClaimType.ABSOLUTE, subject="",
            value=ValueSlot(raw=v_raw, llm_value="", is_inferred=False),
            unit="", aggregation="값", period_type="M",
            period_value=ValueSlot(raw=p_raw, llm_value="", is_inferred=False),
            compare_period_value=(ValueSlot(raw=c_raw, llm_value="", is_inferred=False)
                                  if c_raw else None),
            population="", cited_source="",
        )
        await _normalize_one(claim, base)

    gold = row.get("gold") or {}
    c_pred = claim.compare_period_value.llm_value if claim.compare_period_value else None
    return {
        "row_id": row["row_id"], "stage": 3,
        "label": (gold.get("value") or {}).get("kind"),
        "input": {"claims": [{"value": {"raw": v_raw},
                              "period_value": {"raw": p_raw},
                              "compare_period_value": {"raw": c_raw}}]},
        "output": {"claims": [{"value": {"llm_value": claim.value.llm_value},
                               "period_value": {"llm_value": claim.period_value.llm_value},
                               "compare_period_value": {"llm_value": c_pred}}]},
        "gold": gold,
        "value_gold": (gold.get("value") or {}).get("expected"),
        "value_pred": claim.value.llm_value,
        "period_gold": (gold.get("period") or {}).get("expected"),
        "period_pred": claim.period_value.llm_value,
        "compare_period_gold": (gold.get("compare") or {}).get("expected"),
        "compare_period_pred": c_pred,
        "by_rule": _parse_value(v_raw) is not None,   # 값이 룰로 해소됨(LLM 미사용)
    }


async def main():
    rows = [r for src in SRCS if src.exists() for r in load(src)]
    sem = asyncio.Semaphore(CONCURRENCY)
    records = []
    for fut in asyncio.as_completed([run_one(sem, r) for r in rows]):
        records.append(await fut)
    records.sort(key=lambda r: str(r["row_id"]))

    metrics = score_normalize(records)

    sec = blank_sections()
    sec["개요"] = "3단계 normalize_claim value·period·compare accuracy + 룰 커버리지."
    sec["테스트 방법"] = (f"모듈 격리: 3_source(n={len(rows)}) raw+base 고정 주입, "
                     "_normalize_one 실행, 독립 gold(expected)와 대조.")
    sec["분석"] = "값 오탐 가드(비수치어→허수) 수정 반영 측정."
    sec["한계·주의"] = "gold expected 있는 슬롯만 분모. 일부 period 는 LLM 폴백 포함."

    j, d = save_result(3, "leeaain", records, metrics, sec)
    print(f"[stage 3] n={len(rows)} → {Path(j).name}")
    for m in metrics:
        print("  ", m)


if __name__ == "__main__":
    asyncio.run(main())
