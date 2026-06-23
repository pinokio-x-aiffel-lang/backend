"""현재 파이프라인을 213 SSOT 기사에 1~10단계 실행하고, 각 v2 단계의 INPUT 소스를
단계별 스냅샷으로 저장한다 (테스트셋 v2 재생성용).

비순환: 여기서 만드는 건 input(상류 슬라이스)뿐. gold는 별도 스크립트가 독립 출처
(SSOT figure·병인님·KOSIS raw)에서 재부착한다.  → memory: testset-regen-input-not-gold

스냅샷 지점(=각 v2 단계 input 생산자):
  after2 → 3_normalize input(value.raw) / after4 → 5_fetch(candidates)
  after5 → 6_rank(evidences pre-rank) / after6 → 7_metric(evidences post-rank)
  after7 → 8_alignment(metric) / after9 → 10_explanation(claim_result)

실행: uv run x python benchmark_aain/capture_pipeline_v2.py [--limit N] [--concurrency K]
출력: benchmark_aain/data/260619_capture_v2_snapshots.jsonl  (한 줄=한 row)
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import time
from pathlib import Path

from src.modules.calculate_metric import calculate_metric
from src.modules.check_alignment import check_alignment
from src.modules.decide_verdict import decide_verdict
from src.modules.extract_statistical_claims import extract_statistical_claims
from src.modules.fetch_kosis_data import fetch_kosis_data
from src.modules.generate_explanation import generate_explanation
from src.modules.load_article import load_article, resolve_published_at_from_web
from src.modules.normalize_claim import normalize_claim
from src.modules.rank_evidence import rank_evidence
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.schemas.runtime import MasterSchema

ROOT = Path(__file__).resolve().parent.parent
SSOT = ROOT / "benchmark/data/ssot/260614_master_eval_213_parsed_human_checked_SSOT.jsonl"
OUT = ROOT / "benchmark_aain/data/260619_capture_v2_snapshots.jsonl"

STEPS = [
    (1, load_article), (2, extract_statistical_claims), (3, normalize_claim),
    (4, retrieve_kosis_candidates), (5, fetch_kosis_data), (6, rank_evidence),
    (7, calculate_metric), (8, check_alignment), (9, decide_verdict), (10, generate_explanation),
]
SNAP_AFTER = {2, 4, 5, 6, 7, 9}  # 각 v2 단계 input 소스


def _load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


async def run_one(sem, row):
    async with sem:
        # 발행일 웹서치(네이버) — 더미 대신 기사별 실제 발행일을 base 로 사용(상대시점 정규화).
        # 못 찾으면 None → load_article 이 더미로 폴백.
        published_at = await asyncio.to_thread(resolve_published_at_from_web, row["text"])
        ms = MasterSchema(content=row["text"], published_at_override=published_at)
        snaps, failed, err = {}, None, None
        t0 = time.time()
        for n, fn in STEPS:
            try:
                await fn(ms)
            except Exception as e:  # noqa: BLE001 — 캡처는 한 행 실패해도 계속
                failed, err = n, f"{type(e).__name__}: {e}"
                break
            if n in SNAP_AFTER:
                snaps[f"after{n}"] = copy.deepcopy(ms.model_dump(mode="json"))
        return {
            "row_id": row["row_id"], "label": row["label"], "text": row["text"],
            "published_at": ms.article.published_at if ms.article else None,
            "published_at_resolved": published_at is not None,  # 웹서치 성공 여부(미성공=더미)
            "failed_step": failed, "error": err, "duration_s": round(time.time() - t0, 1),
            "snapshots": snaps,
        }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--out", type=str, default=str(OUT))  # 기본=260619 캡처(보존); 새 캡처는 별도 경로 지정
    a = ap.parse_args()

    out_path = Path(a.out)
    rows = _load(SSOT)
    if a.limit:
        rows = rows[: a.limit]
    sem = asyncio.Semaphore(a.concurrency)
    results = []
    done = 0
    for fut in asyncio.as_completed([run_one(sem, r) for r in rows]):
        rec = await fut
        results.append(rec)
        done += 1
        st = rec["failed_step"]
        print(f"  [{done}/{len(rows)}] row{rec['row_id']} {rec['label']} "
              f"{'FAIL@' + str(st) if st else 'ok'} ({rec['duration_s']}s)", flush=True)

    results.sort(key=lambda r: r["row_id"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for rec in results:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    nfail = sum(1 for r in results if r["failed_step"])
    print(f"\n캡처 {len(results)}행 → 실패 {nfail} | {out_path}")
    # 단계별 도달률
    from collections import Counter
    fc = Counter(r["failed_step"] for r in results if r["failed_step"])
    print("실패 단계 분포:", dict(fc))


if __name__ == "__main__":
    asyncio.run(main())
