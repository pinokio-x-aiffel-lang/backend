"""50개 문장 recall 테스트 v2 — retrieve_kosis_candidates 개선 적용.

변경 사항:
  - _preprocess_subject: 국가 접두어 제거 + 공백 제거
  - _rerank_hits: 시군구통계·국제통계(DT_2*) 후순위 이동

실행:
    infisical run -- uv run python scripts/run_recall_50_v2.py
"""
import asyncio
import json
import os
import time

from dotenv import load_dotenv

load_dotenv()

from src.kosis import search_tables
from src.modules.extract_statistical_claims import extract_statistical_claims
from src.modules.retrieve_kosis_candidates import _preprocess_subject, _rerank_hits
from src.schemas.runtime import Article, MasterSchema

SENTENCES_PATH = "benchmark/recall_50_sentences.json"
OUT_PATH = "scripts/recall_50_results_v2.json"
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
    """subject → (실제 사용된 keyword, KOSIS top-10 후보표 리스트)."""
    keyword = _preprocess_subject(subject)
    try:
        hits = search_tables(keyword, top_n=TOP_N)
        hits = _rerank_hits(hits)
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
    for subj, hits in kosis_results.items():
        kw = keyword_map[subj]
        top3 = [f"{h.get('tbl_nm','?')} [{h.get('stat_nm','?')}]" for h in hits[:3]]
        changed = f" (keyword: {kw!r})" if kw != "".join(subj.split()) else ""
        print(f"     [{subj}]{changed} top3: {top3}")
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
        result = await process_one(item)
        results.append(result)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    total = len(results)
    no_subject = sum(1 for r in results if not r["claims"])
    print(f"{'=' * 60}")
    print(f"완료: {total}건  |  subject 못 찾음: {no_subject}건")
    print(f"결과 저장 -> {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
