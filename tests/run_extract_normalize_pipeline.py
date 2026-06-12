"""2단계(extract_statistical_claims) → 3단계(normalize_claim) 파이프라인을 실문장 100개에 실행.

3_normalize_claim_100_gold.jsonl 의 sentence(src) 만 입력으로 써서:
  Article(content=sentence, published_at=base) → [2] 추출 → [3] 정규화
3단계까지 거친 claim(raw + llm_value)을 JSON output 으로 저장.

    uv run x python tests/run_extract_normalize_pipeline.py
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from src.modules.extract_statistical_claims import (
    ExtractStatisticalClaimsError,
    extract_statistical_claims,
)
from src.modules.normalize_claim import NormalizeClaimError, normalize_claim
from src.schemas.runtime import Article, MasterSchema

GOLD = Path("benchmark/data/3_normalize_claim_100_gold.jsonl")
OUT = Path("tests/results/260612_2-3_extract-normalize_leeaain.json")
sem = asyncio.Semaphore(4)


def _enum(v):
    return getattr(v, "value", v)


def _slot(s):
    return {"raw": s.raw, "llm_value": s.llm_value} if s else None


async def run_one(item):
    sent = item.get("src") or item.get("sentence") or ""
    base = item.get("base", "")
    rec = {"id": item["id"], "sentence": sent, "base": base, "error": None}
    ms = MasterSchema(article=Article(
        article_id=f"g-{item['id']:03d}", content=sent, published_at=base))
    async with sem:
        try:
            await extract_statistical_claims(ms)   # [2]
            await normalize_claim(ms)              # [3]
        except (ExtractStatisticalClaimsError, NormalizeClaimError) as e:
            rec["error"] = str(e)
            rec["claims"] = []
            return rec
    rec["claims"] = [{
        "subject": c.subject,
        "claim_type": _enum(c.claim_type),
        "value": _slot(c.value),
        "unit": c.unit,
        "period_type": _enum(c.period_type),
        "period_value": _slot(c.period_value),
        "compare_period_value": _slot(c.compare_period_value),
    } for c in ms.claims]
    return rec


async def main():
    rows = [json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines() if l.strip()]
    t0 = time.perf_counter()
    out = await asyncio.gather(*[run_one(r) for r in rows])
    dur = time.perf_counter() - t0

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "desc": "[2]extract_statistical_claims → [3]normalize_claim 파이프라인 결과 (100 실문장)",
        "input": str(GOLD), "base": "gold 의 작성일을 article.published_at 로 주입",
        "n_sentences": len(rows), "duration_s": round(dur, 1),
        "results": out,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    n_claims = sum(len(r["claims"]) for r in out)
    n_err = sum(1 for r in out if r["error"])
    n_zero = sum(1 for r in out if not r["claims"] and not r["error"])
    print(f"문장 {len(rows)} | 추출 claim {n_claims} | claim 0개 문장 {n_zero} | 에러 {n_err} | {dur:.1f}s")
    print(f"저장: {OUT}")
    for r in out:
        if r["claims"]:
            print("\n[샘플 1건]")
            print(json.dumps(r, ensure_ascii=False, indent=2)[:700])
            break


if __name__ == "__main__":
    asyncio.run(main())
