"""2단계 claim 추출 결과 덤프 — 평가셋 100문장 → 추출된 claim 슬롯 전체를 jsonl로 저장.

benchmark/data/2_single_sentence_for_claim_extractor.jsonl 의 각 sentence 를
Article.content 에 직접 넣어 extract_statistical_claims 만 실행하고,
추출된 Claim 들을 원본 행 메타(id/label/claim_type/note)와 함께 한 줄씩 기록한다.

    uv run x python benchmark/run_claim_extractor.py

대상 모듈: src.modules.extract_statistical_claims
도구 모듈: (load_article 미사용 — Article 직접 구성)
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.modules.extract_statistical_claims import (
    ExtractStatisticalClaimsError,
    extract_statistical_claims,
)
from src.schemas.runtime import Article, MasterSchema

DATA = Path("benchmark/data/2_single_sentence_for_claim_extractor.jsonl")
OUT = Path("benchmark/data/2_claim_extractor_output.jsonl")
CONCURRENCY = 5


async def _run_one(sem: asyncio.Semaphore, row: dict) -> dict:
    """문장 1건 → 2단계 실행 → 추출 claim 전체 슬롯을 dict 로 직렬화."""
    async with sem:
        ms = MasterSchema(
            article=Article(article_id=f"eval-{row['id']:03d}", content=row["sentence"])
        )
        rec = {
            "id": row["id"],
            "label": row["label"],
            "claim_type_gold": row.get("claim_type", ""),
            "note": row.get("note", ""),
            "sentence": row["sentence"],
        }
        try:
            await extract_statistical_claims(ms)
        except ExtractStatisticalClaimsError as e:
            rec.update(error=str(e), n_claims=0, claims=[])
            return rec
        rec.update(
            error=None,
            n_claims=len(ms.claims),
            claims=[c.model_dump(mode="json") for c in ms.claims],
        )
        return rec


async def main() -> None:
    rows = [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines() if l.strip()]
    sem = asyncio.Semaphore(CONCURRENCY)
    results = await asyncio.gather(*[_run_one(sem, r) for r in rows])
    results.sort(key=lambda r: r["id"])

    with OUT.open("w", encoding="utf-8") as f:
        for rec in results:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    n_err = sum(1 for r in results if r["error"])
    n_claims = sum(r["n_claims"] for r in results)
    print(f"입력 {len(rows)}문장 → claim {n_claims}개 추출 (오류 {n_err}건)")
    print(f"저장: {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
