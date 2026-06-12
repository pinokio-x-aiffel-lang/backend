"""3단계 normalize_claim 간단 실행 — source 100건, raw → 정규화값 출력.

    uv run x python tests/run_normalize_simple.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.modules.normalize_claim import normalize_claim
from src.schemas.runtime import Article, Claim, ClaimType, MasterSchema, ValueSlot

SRC = Path("benchmark/data/3_normalize_claim_100_source.jsonl")


def _slot(g: dict | None) -> ValueSlot | None:
    return ValueSlot(raw=g["raw"], llm_value="", is_inferred=False) if g else None


async def _run_one(i: int, row: dict) -> tuple[int, Claim]:
    claim = Claim(
        claim_id=f"src-{i:03d}", article_id=f"src-{i:03d}", sentence="",
        claim_type=ClaimType.VERIFIABLE, subject="", unit="", aggregation="값",
        period_type="Y", population="", cited_source="",
        value=_slot(row["value"]),
        period_value=_slot(row["period_value"]) or ValueSlot(raw="", llm_value="", is_inferred=False),
        compare_period_value=_slot(row["compare_period_value"]),
    )
    ms = MasterSchema(
        article=Article(article_id=f"src-{i:03d}", content="", published_at=row["base"]),
        claims=[claim],
    )
    await normalize_claim(ms)
    return i, claim


async def main() -> None:
    rows = [json.loads(l) for l in SRC.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("//")]
    results = await asyncio.gather(*[_run_one(i, r) for i, r in enumerate(rows, 1)])
    for i, c in sorted(results):
        parts = [f"{c.value.raw} → {c.value.llm_value}"]
        if c.period_value.raw:
            parts.append(f"{c.period_value.raw} → {c.period_value.llm_value}")
        if c.compare_period_value:
            parts.append(f"{c.compare_period_value.raw} → {c.compare_period_value.llm_value}")
        print(f"{i:3d}  " + "  |  ".join(parts))


if __name__ == "__main__":
    asyncio.run(main())
