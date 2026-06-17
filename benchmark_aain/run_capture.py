"""마스터 213문장을 1~8단계에 통과시켜 각 단계 입력/출력을 실제 캡처.

각 단계 입력(claim 슬롯, KOSIS candidates, evidences, 정규화값, metric verdict)은
'지어내면 안 되는' 실제 데이터다 → 실제 파이프라인을 1회 돌려 캡처한다(라이브 KOSIS/LLM).
verdict 정답은 캡처가 아니라 마스터 라벨을 쓴다(옵션 ②). 여기선 입력 재료만 모은다.

입력(읽기만): benchmark_aain/data/260614_master_eval_213_parsed_human_checked.jsonl
출력(신규):   benchmark_aain/data/260614_capture_master_stage1to8.json

실행(시크릿 주입 필수):
    uv run x python benchmark_aain/run_capture.py [--limit N] [--concurrency K]

규칙: 기존 파일 수정 없음. 한 문장이 어느 단계에서 raise 하면 그 지점 기록 후 계속.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from src.modules.calculate_metric import calculate_metric
from src.modules.check_alignment import check_alignment
from src.modules.extract_statistical_claims import extract_statistical_claims
from src.modules.fetch_kosis_data import fetch_kosis_data
from src.modules.load_article import load_article
from src.modules.normalize_claim import normalize_claim
from src.modules.rank_evidence import rank_evidence
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.schemas.runtime import MasterSchema

ROOT = Path(__file__).resolve().parent.parent
SPINE = ROOT / "benchmark_aain/data/260614_master_eval_213_parsed_human_checked.jsonl"
OUT = ROOT / "benchmark_aain/data/260614_capture_master_stage1to8.json"

# runner.py 와 동일 배선 (1~8단계만; 9=결정적 집계, 10=LLM 총평은 별도 구성).
STEPS = [
    (1, "load_article", load_article),
    (2, "extract_statistical_claims", extract_statistical_claims),
    (3, "normalize_claim", normalize_claim),
    (4, "retrieve_kosis_candidates", retrieve_kosis_candidates),
    (5, "fetch_kosis_data", fetch_kosis_data),
    (6, "rank_evidence", rank_evidence),
    (7, "calculate_metric", calculate_metric),
    (8, "check_alignment", check_alignment),
]


async def _run_one(row: dict, sem: asyncio.Semaphore) -> dict:
    text = row.get("text", "")
    ms = MasterSchema(content=text)
    failed_step = failed_name = error = None
    t0 = time.perf_counter()
    async with sem:
        for step, name, fn in STEPS:
            try:
                await fn(ms)
            except Exception as exc:  # 단계 raise 흡수 → 실패 기록 후 중단
                failed_step, failed_name, error = step, name, str(exc)
                break
    return {
        "row_id": row.get("row_id"),
        "label": row.get("label"),
        "figure_raw": row.get("figure_raw"),
        "gold_figures": row.get("gold_figures"),
        "ok": failed_step is None,
        "failed_step": failed_step,
        "failed_name": failed_name,
        "error": error,
        "duration_s": round(time.perf_counter() - t0, 2),
        "result": ms.model_dump(),
    }


async def _main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()

    rows = [
        json.loads(ln)
        for ln in SPINE.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    if args.limit:
        rows = rows[: args.limit]

    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.perf_counter()
    results = await asyncio.gather(*(_run_one(r, sem) for r in rows))
    dur = time.perf_counter() - t0

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for r in results if r["ok"])
    from collections import Counter
    fail_at = Counter(r["failed_name"] for r in results if not r["ok"])
    print(f"captured {len(results)} rows in {dur:.1f}s -> {OUT.relative_to(ROOT)}")
    print(f"ok={ok} fail={len(results)-ok}  fail_at={dict(fail_at)}")


if __name__ == "__main__":
    asyncio.run(_main())
