"""2_single_sentence_for_claim_extractor.jsonl 의 각 sentence 를 1~5단계만 통과시켜 JSON 저장.

각 줄의 "sentence" 를 content 로 MasterSchema 를 만들고
  [1] load_article → [2] extract_statistical_claims → [3] normalize_claim
  → [4] retrieve_kosis_candidates → [5] fetch_kosis_data
까지만 순서대로 실행한다(6단계 이후는 돌리지 않음). 한 문장이 어느 단계에서
raise 하면 그 지점을 기록하고 다음 문장으로 계속 진행한다.

결과: items[*] = {id, sentence, label, claim_type_gold, ok, failed_step, error,
                  duration_s, result(=master_schema.model_dump())}.

실행(시크릿 주입):
    uv run x python benchmark/run_stage1to5.py [--limit N] [--concurrency K]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from src.modules.extract_statistical_claims import extract_statistical_claims
from src.modules.fetch_kosis_data import fetch_kosis_data
from src.modules.load_article import load_article
from src.modules.normalize_claim import normalize_claim
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.schemas.runtime import MasterSchema

DEFAULT_DATA = Path(__file__).resolve().parent / "data" / "2_single_sentence_for_claim_extractor.jsonl"
DEFAULT_OUT = Path(__file__).resolve().parent / "data" / "2_single_sentence_stage1to5_output.json"

# 1~5단계만 (번호, 이름, 함수). runner.py 배선과 동일.
STEPS = [
    (1, "load_article", load_article),
    (2, "extract_statistical_claims", extract_statistical_claims),
    (3, "normalize_claim", normalize_claim),
    (4, "retrieve_kosis_candidates", retrieve_kosis_candidates),
    (5, "fetch_kosis_data", fetch_kosis_data),
]


async def _run_one(row: dict) -> dict:
    """문장 1건을 1~5단계 순차 실행. 단계 raise 는 흡수해 실패로 기록(다음 문장 계속)."""
    sentence = row.get("sentence", "")
    ms = MasterSchema(content=sentence)
    failed_step = failed_name = error = None
    t0 = time.perf_counter()
    for step, name, fn in STEPS:
        try:
            await fn(ms)
        except Exception as exc:  # 단계 함수 raise → 여기서 흡수
            failed_step, failed_name, error = step, name, str(exc)
            break
    dur = time.perf_counter() - t0
    return {
        "id": row.get("id"),
        "sentence": sentence,
        "label": row.get("label"),
        "claim_type_gold": row.get("claim_type"),
        "ok": error is None,
        "failed_step": failed_step,
        "failed_name": failed_name,
        "error": error,
        "duration_s": round(dur, 2),
        "result": ms.model_dump(),  # article / claims / analysis (verifications=None)
    }


def _print_progress(item: dict, total: int, done: list[int]) -> None:
    done[0] += 1
    head = (item["sentence"] or "")[:34].replace("\n", " ")
    res = item["result"]
    n_claims = len(res.get("claims") or [])
    n_ev = sum(len(a.get("evidences") or []) for a in (res.get("analysis") or []))
    if item["ok"]:
        print(f"[{done[0]:>3}/{total}] OK   {item['duration_s']:5.1f}s  claims={n_claims} ev={n_ev} | {head}…")
    else:
        print(f"[{done[0]:>3}/{total}] FAIL {item['duration_s']:5.1f}s @[{item['failed_step']}] "
              f"{item['failed_name']}: {item['error']} | {head}…")


async def _run_all(rows: list[dict], concurrency: int) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)
    total = len(rows)
    done = [0]

    async def _guarded(row: dict) -> dict:
        async with sem:
            item = await _run_one(row)
            _print_progress(item, total, done)
            return item

    items = await asyncio.gather(*(_guarded(r) for r in rows))
    return sorted(items, key=lambda x: (x["id"] is None, x["id"]))


def _read_jsonl(path: Path, limit: int) -> list[dict]:
    """JSON 객체 줄만 파싱. 빈 줄·주석/설명 줄('{' 로 시작 안 함)은 건너뛴다."""
    rows = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if s.startswith("{"):
            rows.append(json.loads(s))
    return rows[:limit] if limit else rows


def _summary(items: list[dict]) -> dict:
    ok = [i for i in items if i["ok"]]
    fail = [i for i in items if not i["ok"]]
    by_step: dict[str, int] = {}
    for i in fail:
        k = f"[{i['failed_step']}] {i['failed_name']}"
        by_step[k] = by_step.get(k, 0) + 1
    total_claims = sum(len(i["result"].get("claims") or []) for i in items)
    total_ev = sum(
        len(a.get("evidences") or [])
        for i in items for a in (i["result"].get("analysis") or [])
    )
    with_ev = sum(
        1 for i in items
        if any((a.get("evidences") or []) for a in (i["result"].get("analysis") or []))
    )
    return {
        "total": len(items),
        "ok": len(ok),
        "fail": len(fail),
        "fail_by_step": by_step,
        "total_claims_extracted": total_claims,
        "total_evidences_matched": total_ev,
        "sentences_with_any_evidence": with_ev,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="단일 문장 jsonl → 1~5단계 실행 → JSON 저장")
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=0, help="앞 N건만 (0=전체)")
    ap.add_argument("--concurrency", type=int, default=6, help="동시 실행 문장 수")
    args = ap.parse_args()

    rows = _read_jsonl(args.data, args.limit)
    if not rows:
        raise SystemExit(f"실행할 문장 없음: {args.data}")
    print(f"1~5단계 실행 시작 — {len(rows)}건, 동시 {args.concurrency}\n")

    items = asyncio.run(_run_all(rows, args.concurrency))
    summary = _summary(items)

    payload = {"source": str(args.data), "stages": "1-5", "summary": summary, "items": items}
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n{summary}\n저장: {args.out}")


if __name__ == "__main__":
    main()
