"""claim 추출(2단계) detection P/R/F1 평가 — load_article 건너뛰고 직접 호출.

benchmark/data/2_single_sentence_for_claim_extractor.jsonl(양성50+음성50)을 입력으로,
각 문장을 Article.content 에 직접 넣어 extract_statistical_claims 만 실행한다.
판정: non-NONE claim 1개 이상 → predicted positive.
음성은 clean 36 + 경계 14(note `경계:`)라, 전체/엄격 두 컷으로 P/R/F1 을 낸다.
temperature=0 고정 효과를 보려 N_RUNS회 반복하고 run 간 pred 변동(결정성)도 검사한다.

    uv run x python tests/eval_claim_extractor_prf.py

대상 모듈: src.modules.extract_statistical_claims
도구 모듈: (load_article 미사용 — Article 직접 구성)
작성자: leeaain2027
작성일: 2026-06-11
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
from pathlib import Path

from src.modules.extract_statistical_claims import (
    ExtractStatisticalClaimsError,
    extract_statistical_claims,
)
from src.schemas.runtime import Article, ClaimType, MasterSchema

DATA = Path("benchmark/data/2_single_sentence_for_claim_extractor.jsonl")
OUT_DIR = Path("tests/results")
DATE = "260611"
CONCURRENCY = 6
N_RUNS = 3


async def _run_one(sem: asyncio.Semaphore, row: dict) -> dict:
    """문장 1건 → 2단계 직접 실행 → non-NONE claim 수로 pred 판정."""
    async with sem:
        ms = MasterSchema(
            article=Article(article_id=f"eval-{row['id']:03d}", content=row["sentence"])
        )
        rec = {"id": row["id"], "label": row["label"], "note": row.get("note", "")}
        try:
            await extract_statistical_claims(ms)
        except ExtractStatisticalClaimsError as e:
            rec.update(error=str(e), n_total=None, n_nonnone=None, pred=None)
            return rec
        non_none = [c for c in ms.claims if c.claim_type != ClaimType.NONE]
        rec.update(error=None, n_total=len(ms.claims), n_nonnone=len(non_none),
                   pred="positive" if len(non_none) >= 1 else "negative")
        return rec


def _prf(recs: list[dict]) -> dict:
    tp = sum(1 for r in recs if r["label"] == "positive" and r["pred"] == "positive")
    fp = sum(1 for r in recs if r["label"] == "negative" and r["pred"] == "positive")
    fn = sum(1 for r in recs if r["label"] == "positive" and r["pred"] == "negative")
    tn = sum(1 for r in recs if r["label"] == "negative" and r["pred"] == "negative")
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4)}


def _metrics(ok: list[dict]) -> tuple[dict, dict]:
    full = _prf(ok)
    strict_set = [r for r in ok if not (r["label"] == "negative" and r["note"].startswith("경계"))]
    return full, _prf(strict_set)


async def main() -> None:
    rows = [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines() if l.strip()]
    sem = asyncio.Semaphore(CONCURRENCY)

    runs = []
    preds_by_id: dict[int, list] = {r["id"]: [] for r in rows}
    t0 = time.perf_counter()
    for k in range(1, N_RUNS + 1):
        results = await asyncio.gather(*[_run_one(sem, r) for r in rows])
        ok = [r for r in results if r["error"] is None]
        for r in results:
            preds_by_id[r["id"]].append(r["pred"])
        full, strict = _metrics(ok)
        runs.append({"run": k, "n_ok": len(ok), "n_error": len(results) - len(ok),
                     "full": full, "strict": strict, "results": results})
        print(f"  run {k}/{N_RUNS}: full F1={full['f1']} (P={full['precision']} R={full['recall']}) | "
              f"strict F1={strict['f1']} (P={strict['precision']} R={strict['recall']})")
    dur = time.perf_counter() - t0

    # run 간 pred 변동(결정성)
    flips = [i for i, ps in preds_by_id.items() if len(set(ps)) > 1]

    def agg(key, sub):
        vals = [r[key][sub] for r in runs]
        return {"mean": round(statistics.mean(vals), 4),
                "min": round(min(vals), 4), "max": round(max(vals), 4)}

    summary = {sub: {"full": agg("full", sub), "strict": agg("strict", sub)}
               for sub in ("precision", "recall", "f1")}

    # 마지막 run 기준 FP/FN (검토용)
    last_ok = [r for r in runs[-1]["results"] if r["error"] is None]
    fp_list = [r for r in last_ok if r["label"] == "negative" and r["pred"] == "positive"]
    fn_list = [r for r in last_ok if r["label"] == "positive" and r["pred"] == "negative"]

    OUT_DIR.mkdir(exist_ok=True)
    out_json = OUT_DIR / f"{DATE}_2_claim-extractor_leeaain.json"
    out_json.write_text(json.dumps({
        "module": "extract_statistical_claims", "input": str(DATA),
        "model": "HCX-007(hyperclova) temperature=0.0 max_tokens=2048 (EXTRACT_CLAIMS preset)",
        "note": "detection P/R/F1 (non-NONE claim>=1 => positive). load_article 미사용.",
        "n": len(rows), "n_runs": N_RUNS, "duration_s": round(dur, 1),
        "pred_flips_across_runs": flips, "summary": summary, "runs": runs,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 62)
    print("claim 추출(2단계) detection P/R/F1  — HCX-007, temperature=0.0, 3회")
    print("=" * 62)
    print(f"입력 {len(rows)}문장 × {N_RUNS}회 | {dur:.1f}s (동시성 {CONCURRENCY})")
    print(f"run 간 pred 변동(결정성): {len(flips)}건 {flips if flips else '(완전 일치)'}\n")
    for cut in ("full", "strict"):
        s = {m: summary[m][cut] for m in ("precision", "recall", "f1")}
        title = "전체 (양성50+음성50)" if cut == "full" else "엄격 (양성50+clean음성36)"
        print(f"[{title}]  (mean[min~max])")
        print(f"  Precision={s['precision']['mean']} [{s['precision']['min']}~{s['precision']['max']}]")
        print(f"  Recall   ={s['recall']['mean']} [{s['recall']['min']}~{s['recall']['max']}]")
        print(f"  F1       ={s['f1']['mean']} [{s['f1']['min']}~{s['f1']['max']}]\n")
    print(f"[마지막 run FP {len(fp_list)} / FN {len(fn_list)}]")
    for r in fp_list:
        print(f"  FP id={r['id']} [{r['note']}]")
    for r in fn_list:
        print(f"  FN id={r['id']}")
    print(f"\n저장: {out_json}")
    print("⚠ Precision 은 hard-negative 기준 보수치(운영 대표값 아님).")


if __name__ == "__main__":
    asyncio.run(main())
