"""stage2 compare_period_raw 추출 강화 검증 — 명시 비교기준 기사에 실제 재추출.

after6 캡처에서 '전년 동월 대비' 등 명시 비교를 가졌으나 추출기가 놓친 기사들을
강화 프롬프트로 재추출 → change_rate claim 의 compare_period_raw 채움 여부 확인.
before = 캡처(구프롬프트, 미추출). after = 본 재실행.
실행: uv run x python benchmark_aain/diag_stage2_compare_extract.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.modules.extract_statistical_claims import extract_statistical_claims
from src.schemas.runtime import MasterSchema

ROOT = Path(__file__).resolve().parent.parent
CAP = ROOT / "benchmark_aain/data/260619_capture_v2_snapshots.jsonl"
TARGETS = {34, 48, 56, 58, 63, 66, 67, 90, 120}


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


async def main():
    cap = load(CAP)
    after6 = {r["row_id"]: r["snapshots"]["after6"] for r in cap
              if r["snapshots"].get("after6") and r["row_id"] in TARGETS}
    sem = asyncio.Semaphore(4)

    async def one(rid, snap):
        async with sem:
            ms = MasterSchema.model_validate(snap)
            ms.claims = []
            await extract_statistical_claims(ms)
            rows = []
            for c in ms.claims:
                if c.claim_type.value == "change_rate":
                    cp = c.compare_period_value.raw if c.compare_period_value else None
                    rows.append((c.sentence[:48], cp))
            return rid, rows

    results = await asyncio.gather(*[one(rid, s) for rid, s in after6.items()])
    tot = hit = 0
    for rid, rows in sorted(results):
        print(f"row {rid}:")
        for sent, cp in rows:
            tot += 1
            hit += bool(cp)
            print(f"   {'O' if cp else 'X'} cp={cp!r} | {sent}")
    print(f"\n=== change_rate claim 중 compare_period_raw 채워짐: {hit}/{tot} (before=0) ===")


if __name__ == "__main__":
    asyncio.run(main())
