"""T 골드셋 123건으로 [2]+[3]+map_claim_via_meta([4+5 대안]) 경로 평가.

SSOT: data/260614_master_eval_213_parsed_human_checked_SSOT.jsonl (label=T 123건)

평가 지표:
  sentence_hit  : gold_figure 1건 이상 매칭된 문장 수 / 전체 문장 수
  gold_recall   : 매칭된 scalar gold_figure 수 / 전체 scalar gold_figure 수

Langfuse 트레이싱: 각 문장을 t123:{row_id} 루트 span 으로 기록.

실행:
  infisical run --env dev --recursive -- python -c "
import sys; sys.path.insert(0,'.'); import runpy
runpy.run_path('benchmark/260618_2~5_t123-meta-path_innnn/260618_2~5_t123-meta-path_innnn.py', run_name='__main__')
" -- --limit 5
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from src.modules.extract_statistical_claims import extract_statistical_claims  # noqa: E402
from src.modules.map_claim_via_meta import map_claim_via_meta  # noqa: E402
from src.modules.normalize_claim import normalize_claim  # noqa: E402
from src.observability import flush, instrument_kosis, run_pipeline_traced  # noqa: E402
from src.schemas.runtime import Article, MasterSchema  # noqa: E402

_SSOT = _REPO / "data" / "260614_master_eval_213_parsed_human_checked_SSOT.jsonl"
_OUT_DIR = Path(__file__).parent
_BASE = Path(__file__).stem  # "260618_2~5_t123-meta-path_innnn"


def _save(results: list[dict], path: Path) -> None:
    n = len(results)
    hits = sum(r["sentence_hit"] for r in results)
    errors = sum(1 for r in results if r["error"])
    total_scalar = sum(r["scalar_total"] for r in results)
    total_matched = sum(r["scalar_matched"] for r in results)
    summary = {
        "sentence_hit": hits,
        "sentence_total": n,
        "sentence_hit_rate": round(hits / n, 4) if n else 0.0,
        "gold_matched": total_matched,
        "gold_total": total_scalar,
        "gold_recall": round(total_matched / total_scalar, 4) if total_scalar else 0.0,
        "errors": errors,
    }
    path.write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _infer_published_at(gold_figures: list[dict]) -> str | None:
    """gold_figures 의 최신 기간 + 1개월 → 발행일 추정(상대 날짜 정규화 기준)."""
    periods: list[tuple[int, int]] = []
    for gf in gold_figures:
        p = gf.get("period") or ""
        # "2025-03" 또는 "2025-01~2025-03" — 뒤쪽 연·월만 사용
        chunk = p.split("~")[-1] if "~" in p else p
        if len(chunk) >= 7 and chunk[4] == "-":
            try:
                periods.append((int(chunk[:4]), int(chunk[5:7])))
            except ValueError:
                pass
    if not periods:
        return None
    y, m = max(periods)
    m += 1
    if m > 12:
        y, m = y + 1, 1
    return f"{y}-{m:02d}-01"


def _ev_values(ms: MasterSchema) -> list[float]:
    return [ev.value for an in ms.analysis for ev in an.evidences if ev.value is not None]


def _match_gold(ev_values: list[float], gold_figures: list[dict]) -> list[bool | None]:
    """각 gold_figure 에 대해 매칭 여부. list value 는 None(skip)."""
    result = []
    for gf in gold_figures:
        gv = gf.get("value")
        if isinstance(gv, list) or gv is None:
            result.append(None)
            continue
        tol = max(0.1, abs(gv) * 0.005)
        result.append(any(abs(ev - gv) <= tol for ev in ev_values))
    return result


async def _run_one(entry: dict) -> dict:
    instrument_kosis()
    row_id = entry["row_id"]
    text = entry["text"]
    gold = entry["gold_figures"]

    ms = MasterSchema(content=text)
    ms.article = Article(
        article_id=str(row_id),
        content=text,
        published_at=_infer_published_at(gold),
    )

    err = await run_pipeline_traced(
        ms,
        (extract_statistical_claims, normalize_claim, map_claim_via_meta),
        root_name=f"t123:{row_id}",
        metadata={"row_id": row_id, "text": text[:120]},
    )

    ev_vals = _ev_values(ms)
    matched = _match_gold(ev_vals, gold)
    scalar_results = [(m, gf) for m, gf in zip(matched, gold) if m is not None]

    return {
        "row_id": row_id,
        "n_claims": len(ms.claims),
        "ev_values": ev_vals,
        "gold_values": [gf["value"] for gf in gold],
        "matched": matched,
        "sentence_hit": any(m is True for m in matched),
        "scalar_total": len(scalar_results),
        "scalar_matched": sum(1 for m, _ in scalar_results if m),
        "error": err,
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0=전체 123건")
    ap.add_argument("--ids", default="", help="특정 row_id만(쉼표): 2,6,7,8")
    ap.add_argument("--select-model", default="hcx", choices=["hcx", "claude"],
                    help="SELECT_KOSIS_CELL 모델 선택 (기본: hcx)")
    args = ap.parse_args()

    if args.select_model == "claude":
        os.environ["KOSIS_SELECT_MODEL"] = "claude"

    records = [
        json.loads(l) for l in _SSOT.read_text(encoding="utf-8").splitlines() if l.strip()
    ]
    items = [r for r in records if r.get("label") == "T"]
    if args.ids:
        want = {int(i) for i in args.ids.split(",") if i.strip()}
        items = [r for r in items if r["row_id"] in want]
    elif args.limit:
        items = items[: args.limit]

    model_tag = args.select_model
    out_path = _OUT_DIR / f"{_BASE}_result_{model_tag}.json"
    print(f"=== t123 map_claim_via_meta eval ({len(items)}건) [select={model_tag}] ===", flush=True)
    results = []
    for i, entry in enumerate(items, 1):
        res = await _run_one(entry)
        tag = "HIT" if res["sentence_hit"] else ("ERR" if res["error"] else "---")
        print(
            f"  {i:>3}/{len(items)} row={res['row_id']:>3} [{tag}]"
            f"  claims={res['n_claims']}"
            f"  ev={res['ev_values']}"
            f"  gold={res['gold_values']}",
            flush=True,
        )
        results.append(res)
        # 항목마다 중간 저장 — 프로세스 종료 시에도 부분 결과 보존
        _save(results, out_path)

    flush()

    out = out_path
    _save(results, out)

    n = len(results)
    summary = json.loads(out.read_text(encoding="utf-8"))["summary"]
    print(f"\n=== 결과 ===", flush=True)
    print(f"  sentence_hit : {summary['sentence_hit']}/{n} = {summary['sentence_hit_rate']:.1%}", flush=True)
    print(f"  gold_recall  : {summary['gold_matched']}/{summary['gold_total']} = {summary['gold_recall']:.1%}", flush=True)
    print(f"  errors       : {summary['errors']}", flush=True)
    print(f"→ {out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
