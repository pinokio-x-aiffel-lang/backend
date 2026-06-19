"""[2] extract_statistical_claims 평가 — 문장 P/R/F1 + claim_type accuracy.

모듈 격리: 입력=평가셋 문장(양성50+음성50, 사람 라벨), gold=label(claim 여부)·ctype_gold.
양성=수치주장 있음(claim 추출 기대), 음성=hard-negative(추출 기대 안 함).
실행: uv run x python benchmark/eval_stage2.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from benchmark.reporting import save_result, blank_sections
from benchmark.scoring import score_extract
from src.modules.extract_statistical_claims import (
    ExtractStatisticalClaimsError, extract_statistical_claims,
)
from src.schemas.runtime import Article, MasterSchema

SRC = Path("benchmark/data/2_claim/2_source_1.jsonl")
CONCURRENCY = 5


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def stat_claims(claims):
    """claim_type != NONE 인 통계 주장만."""
    out = []
    for c in claims:
        ct = c.claim_type.value if hasattr(c.claim_type, "value") else c.claim_type
        if ct and ct != "none":
            out.append(c)
    return out


async def run_one(sem, row):
    async with sem:
        ms = MasterSchema(content=row["src_text"])
        ms.article = Article(article_id=str(row.get("src_id")), content=row["src_text"])
        try:
            await extract_statistical_claims(ms)
            sc = stat_claims(ms.claims)
        except ExtractStatisticalClaimsError:
            sc = []
        gold_claim = (row.get("gold_n_claims") or 0) >= 1  # 양성=claim 있음
        pred_claim = len(sc) >= 1
        rec = {
            "row_id": row.get("src_id"), "stage": 2,
            "input": {"article": {"content": row["src_text"]}},
            "output": {"n_claims": len(sc),
                       "claim_types": [(c.claim_type.value if hasattr(c.claim_type, "value") else c.claim_type) for c in sc]},
            "gold_claim": gold_claim, "pred_claim": pred_claim,
        }
        if row.get("ctype_gold") and sc:  # claim_type accuracy(양성·추출성공만)
            rec["ctype_gold"] = row["ctype_gold"]
            rec["ctype_pred"] = sc[0].claim_type.value if hasattr(sc[0].claim_type, "value") else sc[0].claim_type
        return rec


async def main():
    rows = [r for r in load(SRC) if r.get("gold_n_claims") is not None]  # eval셋 100
    sem = asyncio.Semaphore(CONCURRENCY)
    records = []
    done = 0
    for fut in asyncio.as_completed([run_one(sem, r) for r in rows]):
        records.append(await fut)
        done += 1
        if done % 20 == 0:
            print(f"  {done}/{len(rows)}", flush=True)
    records.sort(key=lambda r: r["row_id"])

    metrics = score_extract(records)
    sec = blank_sections()
    sec["개요"] = "2단계 extract_statistical_claims — 문장 P/R/F1 + claim_type accuracy. 양성50(수치주장)+음성50(hard-negative)."
    sec["테스트 방법"] = ("모듈 격리: 평가셋 문장(사람 라벨)을 Article.content 로 추출 실행. "
                     "pred_claim=통계 claim(type≠NONE) 추출 여부, gold_claim=label(양성). "
                     "claim_type=양성·추출성공 행만 ctype_gold↔ctype_pred. 데이터=2_source_1.jsonl(gold 100행).")
    sec["분석"] = "Precision 은 hard-negative 보수치(음성50이 어려운 비-claim)."
    sec["한계·주의"] = "음성=hard-negative만이라 Precision 보수적. claim_type 은 양성 추출성공 분모."
    j, d = save_result(2, "leeaain", records, metrics, sec)
    print(f"[stage 2] records={len(records)} → {j.name}")
    for m in metrics:
        print(f"   {m['지표']} {m['값']} {m.get('95% CI','')}")


if __name__ == "__main__":
    asyncio.run(main())
