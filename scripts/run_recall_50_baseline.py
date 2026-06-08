"""50개 문장 recall 테스트 baseline — 개선 전 파이프라인 재현.

조건:
  - 공백 제거 O  ("".join(subject.split()))
  - 국가 접두어 제거 X
  - 시군구·국제통계 재정렬 X

실행:
    infisical run -- uv run python scripts/run_recall_50_baseline.py
"""
import asyncio
import json
import os
import time

from dotenv import load_dotenv

load_dotenv()

from src.kosis import search_tables
from src.modules.extract_statistical_claims import extract_statistical_claims
from src.schemas.runtime import Article, MasterSchema

SENTENCES_PATH = "benchmark/recall_50_sentences.json"
OUT_PATH = "scripts/recall_50_results_baseline.json"
TOP_N = 10


async def extract_claims_full(sentence: str, idx: int) -> list[dict]:
    ms = MasterSchema(
        article=Article(article_id=f"recall-{idx:03d}", title="", content=sentence)
    )
    await extract_statistical_claims(ms)
    return [
        {
            "claim_id": c.claim_id,
            "claim_type": c.claim_type.value if c.claim_type else "",
            "subject": c.subject,
            "value_raw": c.value.raw if c.value else "",
            "unit": c.unit,
            "period_type": c.period_type,
            "period_raw": c.period_value.raw if c.period_value else "",
            "population": c.population,
            "cited_source": c.cited_source,
        }
        for c in ms.claims
    ]


def search_kosis(subject: str) -> tuple[str, list[dict]]:
    keyword = "".join(subject.split())
    try:
        hits = search_tables(keyword, top_n=TOP_N)
        return keyword, [
            {
                "rank": i + 1,
                "tbl_id": h.tbl_id,
                "tbl_nm": h.tbl_nm,
                "stat_nm": h.stat_nm,
                "org_nm": h.org_nm,
            }
            for i, h in enumerate(hits)
        ]
    except Exception as e:
        return keyword, [{"error": str(e)}]


async def process_one(item: dict) -> dict:
    idx = item["idx"]
    sentence = item["sentence"]
    print(f"[{idx:>2}/50] 처리 중...")
    t0 = time.perf_counter()

    claims = await extract_claims_full(sentence, idx)
    subjects = [c["subject"] for c in claims if c["subject"] and c["subject"] != "불명"]

    kosis_results = {}
    keyword_map = {}
    for subj in subjects:
        keyword, hits = search_kosis(subj)
        kosis_results[subj] = hits
        keyword_map[subj] = keyword

    elapsed = int((time.perf_counter() - t0) * 1000)
    print(f"     claims: {[c['subject'] for c in claims]}")
    print()

    return {
        "idx": idx,
        "sentence": sentence,
        "claims": claims,
        "kosis": kosis_results,
        "keyword_map": keyword_map,
        "elapsed_ms": elapsed,
    }


async def main():
    if not os.getenv("KOSIS_API_KEY"):
        raise SystemExit("KOSIS_API_KEY 가 .env 에 없습니다.")

    with open(SENTENCES_PATH, encoding="utf-8") as f:
        sentences = json.load(f)

    print(f"총 {len(sentences)}개 문장 처리 시작\n{'=' * 60}")
    results = []
    for item in sentences:
        results.append(await process_one(item))

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"{'=' * 60}")
    print(f"완료: {len(results)}건  |  결과 저장 -> {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
