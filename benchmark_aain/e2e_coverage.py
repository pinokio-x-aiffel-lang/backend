"""E2E coverage 측정 — 전 파이프라인을 행별로 돌려 최종 verdict 분포·coverage 집계.

coverage = (T·F·M 판정 claim) / (전체 claim).  NEI/UNVERIFIED 등 = 미커버.
입력: SSOT(jsonl, 'text' 필드) 또는 텍스트(한 줄=1건). 기본=SSOT 213.
값만 빨리 보려는 용도 — 채점 하니스(save_result) 미사용, 콘솔에 값만 출력.

실행: uv run x python benchmark_aain/e2e_coverage.py [--data path] [--concurrency K] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

from src.pipeline.events import ResultEvent
from src.pipeline.runner import Pipeline

ROOT = Path(__file__).resolve().parent.parent
SSOT = ROOT / "benchmark/data/ssot/260614_master_eval_213_parsed_human_checked_SSOT.jsonl"
COVERED = {"T", "F", "M"}  # 검증 가능 판정. 그 외(NEI/UNVERIFIED/N)=미커버.


def _load(path: Path):
    if path.suffix == ".jsonl":
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        return [(r.get("row_id", i), r["text"]) for i, r in enumerate(rows, 1)]
    raw = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return list(enumerate(raw, 1))


async def _run_one(idx: int, content: str):
    master = None
    err = None
    try:
        async for ev in Pipeline().run(content):
            if isinstance(ev, ResultEvent):
                master = ev.master_schema
    except Exception as e:  # 스모크: 한 건 실패 흡수
        err = str(e)
    return idx, master, err


async def _run_all(lines, conc: int):
    sem = asyncio.Semaphore(conc)

    async def g(i, c):
        async with sem:
            idx, master, err = await _run_one(i, c)
            if master and master.verifications:
                vs = [cr.verdict for cr in (master.verifications.claim_results or [])]
                print(f"[{idx}] claims={len(vs)} {dict(Counter(vs))}", flush=True)
            else:
                print(f"[{idx}] FAIL {err}", flush=True)
            return idx, master, err

    return await asyncio.gather(*(g(i, c) for i, c in lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=SSOT)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    lines = _load(a.data)
    if a.limit:
        lines = lines[: a.limit]
    print(f"E2E coverage 측정 — {len(lines)}건, 동시 {a.concurrency}, data={a.data.name}\n", flush=True)

    res = asyncio.run(_run_all(lines, a.concurrency))

    allv, ok, fail = [], 0, 0
    for _idx, master, _err in res:
        if master and master.verifications:
            ok += 1
            allv += [cr.verdict for cr in (master.verifications.claim_results or [])]
        else:
            fail += 1
    cnt = Counter(allv)
    total = len(allv)
    covered = sum(c for v, c in cnt.items() if v in COVERED)
    cov = covered / total if total else 0.0

    print("\n===== E2E COVERAGE =====", flush=True)
    print(f"기사(행) 성공/실패: {ok}/{fail}", flush=True)
    print(f"전체 claim 수: {total}", flush=True)
    print(f"verdict 분포: {dict(cnt)}", flush=True)
    print(f"covered(T/F/M): {covered}", flush=True)
    print(f"COVERAGE = {covered}/{total} = {cov:.3f}", flush=True)


if __name__ == "__main__":
    main()
