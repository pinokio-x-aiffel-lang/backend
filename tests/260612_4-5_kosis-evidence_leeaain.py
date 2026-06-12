"""4~5단계 KOSIS 검색·조회 — gold src 100문장, 매칭 값 발견 여부 True/False 집계.

benchmark/data/3_normalize_claim_100_gold.jsonl 의 src 를 content 로,
base(작성일)를 article.published_at 으로 주입해 (1단계 생략)
  [2] extract → [3] normalize → [4] retrieve_kosis_candidates → [5] fetch_kosis_data
를 실행한다. found(True) = analysis[*].evidences ≥ 1 (KOSIS 매칭 셀 존재).

    uv run x python tests/260612_4-5_kosis-evidence_leeaain.py

대상 모듈: [4] retrieve_kosis_candidates / [5] fetch_kosis_data
도구 모듈: [2] extract_statistical_claims, [3] normalize_claim (입력 생성용)
작성자: leeaain2027  작성일: 2026-06-12
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
from pathlib import Path

from src.modules.extract_statistical_claims import extract_statistical_claims
from src.modules.fetch_kosis_data import fetch_kosis_data
from src.modules.normalize_claim import normalize_claim
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.schemas.runtime import Article, MasterSchema

GOLD = Path("benchmark/data/3_normalize_claim_100_gold.jsonl")
OUT_DIR = Path("tests/results")
BASE_NAME = "260612_4-5_kosis-evidence_leeaain"
CONCURRENCY = 5

STEPS = [
    (2, "extract_statistical_claims", extract_statistical_claims),
    (3, "normalize_claim", normalize_claim),
    (4, "retrieve_kosis_candidates", retrieve_kosis_candidates),
    (5, "fetch_kosis_data", fetch_kosis_data),
]


async def _run_one(sem: asyncio.Semaphore, row: dict, total: int, done: list) -> dict:
    async with sem:
        ms = MasterSchema(article=Article(
            article_id=f"gold-{row['id']:03d}", content=row["src"],
            published_at=row["base"],
        ))
        failed_step = error = None
        t0 = time.perf_counter()
        for step, name, fn in STEPS:
            try:
                await fn(ms)
            except Exception as exc:
                failed_step, error = step, f"{name}: {exc}"
                break
        dur = time.perf_counter() - t0

        dump = ms.model_dump()
        analysis = dump.get("analysis") or []
        n_ev = sum(len(a.get("evidences") or []) for a in analysis)
        n_claims_ev = sum(1 for a in analysis if a.get("evidences"))
        found = n_ev > 0

        done[0] += 1
        mark = "T" if found else ("E" if error else "F")
        print(f"[{done[0]:>3}/{total}] {mark} {dur:5.1f}s claims={len(dump.get('claims') or [])} "
              f"ev={n_ev}" + (f"  @[{failed_step}] {error[:60]}" if error else ""))
        return {
            "id": row["id"], "base": row["base"], "src": row["src"],
            "found": found, "n_claims": len(dump.get("claims") or []),
            "n_claims_with_evidence": n_claims_ev, "n_evidences": n_ev,
            "failed_step": failed_step, "error": error, "duration_s": round(dur, 2),
        }


async def main() -> None:
    rows = [json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines()
            if l.strip().startswith("{")]
    sem = asyncio.Semaphore(CONCURRENCY)
    done = [0]
    t0 = time.perf_counter()
    results = await asyncio.gather(*[_run_one(sem, r, len(rows), done) for r in rows])
    wall = time.perf_counter() - t0
    results = sorted(results, key=lambda r: r["id"])

    n = len(results)
    t = sum(1 for r in results if r["found"])
    errs = [r for r in results if r["error"]]
    no_claim = [r for r in results if not r["error"] and r["n_claims"] == 0]
    durs = [r["duration_s"] for r in results]
    fail_by_step: dict[str, int] = {}
    for r in errs:
        k = f"[{r['failed_step']}]"
        fail_by_step[k] = fail_by_step.get(k, 0) + 1

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / f"{BASE_NAME}.json").write_text(json.dumps({
        "module": "[4] retrieve_kosis_candidates + [5] fetch_kosis_data",
        "input": str(GOLD), "n": n,
        "criterion": "found=True ⇔ analysis[*].evidences ≥ 1 (KOSIS 매칭 셀 존재)",
        "true": t, "false": n - t, "rate": round(t / n, 4),
        "errors": len(errs), "fail_by_step": fail_by_step,
        "no_claim_sentences": len(no_claim),
        "timing": {"mean_s": round(statistics.mean(durs), 2),
                   "median_s": round(statistics.median(durs), 2),
                   "max_s": round(max(durs), 2), "wall_s": round(wall, 1)},
        "results": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nTrue {t} / False {n - t}  (발견율 {t/n:.1%})")
    print(f"단계 오류 {len(errs)}건 {fail_by_step} / 무claim 문장 {len(no_claim)}건")
    print(f"시간: 평균 {statistics.mean(durs):.1f}s 중앙값 {statistics.median(durs):.1f}s "
          f"최대 {max(durs):.1f}s (벽시계 {wall:.0f}s)")
    print(f"저장: {OUT_DIR}/{BASE_NAME}.json")


if __name__ == "__main__":
    asyncio.run(main())
