"""claim 추출(2단계) detection P/R/F1 평가 — load_article 건너뛰고 직접 호출.

benchmark/data/2_single_sentence_for_claim_extractor.jsonl(양성50+음성50, 단일컷)을 입력으로,
각 문장을 Article.content 에 직접 넣어 extract_statistical_claims 만 실행한다.
판정: non-NONE claim 1개 이상 → predicted positive.
N_RUNS회 반복(결정성 확인) + 항목별(golden/pred/결과/판단근거) md·csv 리포트 생성.

    uv run x python tests/eval_claim_extractor_prf.py

대상 모듈: src.modules.extract_statistical_claims
도구 모듈: (load_article 미사용 — Article 직접 구성)
작성자: leeaain2027
작성일: 2026-06-11
"""
from __future__ import annotations

import asyncio
import csv
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
BASE = "260611_2_claim-extractor_leeaain"
CONCURRENCY = 5
N_RUNS = 3


def _cell(s: str, n: int = 999) -> str:
    s = str(s).replace("|", "/").replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


async def _run_one(sem: asyncio.Semaphore, row: dict) -> dict:
    """문장 1건 → 2단계 직접 실행 → non-NONE claim 수/내용으로 pred 판정."""
    async with sem:
        ms = MasterSchema(
            article=Article(article_id=f"eval-{row['id']:03d}", content=row["sentence"])
        )
        rec = {"id": row["id"], "label": row["label"], "note": row.get("note", ""),
               "claim_type": row.get("claim_type", ""), "sentence": row["sentence"]}
        try:
            await extract_statistical_claims(ms)
        except ExtractStatisticalClaimsError as e:
            rec.update(error=str(e), n_total=None, n_nonnone=None, pred=None, evidence=[])
            return rec
        non_none = [c for c in ms.claims if c.claim_type != ClaimType.NONE]
        rec.update(
            error=None, n_total=len(ms.claims), n_nonnone=len(non_none),
            pred="positive" if non_none else "negative",
            evidence=[f"{c.subject}={c.value.raw}({c.claim_type.value})" for c in non_none],
        )
        return rec


def _outcome(r: dict) -> str:
    g, p = r["label"], r["pred"]
    return {("positive", "positive"): "TP", ("negative", "positive"): "FP",
            ("positive", "negative"): "FN", ("negative", "negative"): "TN"}[(g, p)]


def _prf(recs: list[dict]) -> dict:
    c = {"TP": 0, "FP": 0, "FN": 0, "TN": 0}
    for r in recs:
        c[_outcome(r)] += 1
    p = c["TP"] / (c["TP"] + c["FP"]) if (c["TP"] + c["FP"]) else 0.0
    rc = c["TP"] / (c["TP"] + c["FN"]) if (c["TP"] + c["FN"]) else 0.0
    f1 = 2 * p * rc / (p + rc) if (p + rc) else 0.0
    return {**c, "precision": round(p, 4), "recall": round(rc, 4), "f1": round(f1, 4)}


def _golden(r: dict) -> str:
    return f"pos·{r['claim_type']}" if r["label"] == "positive" else f"neg·{_cell(r['note'], 12)}"


def _row_md(r: dict) -> str:
    ev = _cell(", ".join(r["evidence"]) or "—", 48)
    return f"| {r['id']} | {_golden(r)} | {r['pred']} | {_outcome(r)} | {ev} | {_cell(r['sentence'], 34)} |"


def _table(recs: list[dict]) -> str:
    head = "| id | golden | pred | 결과 | 판단근거(추출 claim) | 문장 |\n|--|--|--|--|--|--|"
    return head + "\n" + "\n".join(_row_md(r) for r in recs)


async def main() -> None:
    rows = [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines() if l.strip()]
    sem = asyncio.Semaphore(CONCURRENCY)

    runs, metrics = [], []
    preds_by_id: dict[int, list] = {r["id"]: [] for r in rows}
    t0 = time.perf_counter()
    for k in range(1, N_RUNS + 1):
        results = await asyncio.gather(*[_run_one(sem, r) for r in rows])
        ok = [r for r in results if r["error"] is None]
        for r in results:
            preds_by_id[r["id"]].append(r["pred"])
        m = _prf(ok)
        metrics.append(m)
        runs.append(results)
        print(f"  run {k}/{N_RUNS}: P={m['precision']} R={m['recall']} F1={m['f1']} "
              f"(TP{m['TP']} FP{m['FP']} FN{m['FN']} TN{m['TN']})")
    dur = time.perf_counter() - t0

    flips = [i for i, ps in preds_by_id.items() if len(set(ps)) > 1]
    agg = {s: {"mean": round(statistics.mean(x[s] for x in metrics), 4),
               "min": round(min(x[s] for x in metrics), 4),
               "max": round(max(x[s] for x in metrics), 4)}
           for s in ("precision", "recall", "f1")}

    last = [r for r in runs[-1] if r["error"] is None]   # 항목별 표 = 마지막 run
    errs = [r for r in last if _outcome(r) in ("FP", "FN")]
    errs.sort(key=lambda r: (r["pred"], r["id"]))

    OUT_DIR.mkdir(exist_ok=True)
    # raw json
    (OUT_DIR / f"{BASE}.json").write_text(json.dumps({
        "module": "extract_statistical_claims",
        "model": "HCX-007(hyperclova) temperature=0.0 max_tokens=2048 (EXTRACT_CLAIMS)",
        "input": str(DATA), "n": len(rows), "n_runs": N_RUNS, "duration_s": round(dur, 1),
        "note": "detection (non-NONE claim>=1 => positive). load_article 미사용. 단일컷(경계 폐기).",
        "summary": agg, "pred_flips_across_runs": flips,
        "runs": runs,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # csv (마지막 run, 엑셀 검토용)
    with (OUT_DIR / f"{BASE}.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "golden", "claim_type/category", "pred", "결과", "n_nonnone",
                    "판단근거", "문장"])
        for r in last:
            cat = r["claim_type"] if r["label"] == "positive" else r["note"]
            w.writerow([r["id"], r["label"], cat, r["pred"], _outcome(r),
                        r["n_nonnone"], " | ".join(r["evidence"]), r["sentence"]])

    # md 리포트
    md = f"""# 2단계 claim 추출 — detection P/R/F1 (항목별)

| 항목 | 내용 |
|---|---|
| ① 목적 | claim 추출기가 "문장에 통계 claim이 있는지"를 맞히는지(탐지) P/R/F1 |
| ② 검증 대상 모듈 | `src.modules.extract_statistical_claims` (2단계) |
| ③ 도구 모듈 | 없음 — load_article 미사용, `Article(content=문장)` 직접 |
| ④ 일자/작성자 | 2026-06-11 / leeaain2027 |

- 입력: `{DATA}` (양성 50 + 음성 50, **단일컷** = 경계 폐기, 전망치·견해·기록추세 모두 비-claim 확정)
- 모델: **HCX-007** temperature=0.0 max_tokens=2048 (`EXTRACT_CLAIMS` preset)
- 판정: non-NONE claim ≥1 → predicted positive
- 실행: 100문장 × {N_RUNS}회 / {dur:.1f}s / 동시성 {CONCURRENCY}
- golden = 기대 라벨(claim 있음/없음 + 카테고리). claim 내용 자체의 golden은 아님(슬롯평가 별도)

## 메트릭 ({N_RUNS}회 mean[min~max])

| Precision | Recall | F1 |
|---|---|---|
| {agg['precision']['mean']} [{agg['precision']['min']}~{agg['precision']['max']}] | {agg['recall']['mean']} [{agg['recall']['min']}~{agg['recall']['max']}] | {agg['f1']['mean']} [{agg['f1']['min']}~{agg['f1']['max']}] |

- run 간 pred 변동(결정성): {len(flips)}건 {flips if flips else '(완전 일치)'} — temperature=0이어도 HCX 서버측 비결정성 존재
- ⚠ Precision 은 hard-negative 기준 보수치(운영 대표값 아님)

## 오답 (마지막 run · FP/FN {len(errs)}건)

{_table(errs) if errs else '_없음_'}

## 전체 항목 (마지막 run · 100건)

{_table(last)}
"""
    (OUT_DIR / f"{BASE}.md").write_text(md, encoding="utf-8")

    print(f"\n메트릭({N_RUNS}회 평균): P={agg['precision']['mean']} R={agg['recall']['mean']} F1={agg['f1']['mean']}")
    print(f"결정성 변동: {len(flips)}건 {flips}")
    print(f"오답(마지막 run): {len(errs)}건")
    print(f"저장: {OUT_DIR}/{BASE}.{{md,json,csv}}")


if __name__ == "__main__":
    asyncio.run(main())
