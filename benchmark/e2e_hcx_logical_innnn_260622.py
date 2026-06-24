"""E2E 벤치마크: 아인님 logical 파이프라인 (retrieve+fetch) + Langfuse 트레이싱.

입력  : SSOT 213행 (T123/F30/M30/NEI30)
파이프라인 : 1→2→3→4(retrieve_kosis_candidates)→5(fetch_kosis_data)→6→7→8→9→10
비교 대상 : e2e_hcx_agent (map_claim_via_agent 사용) vs 이 스크립트

측정 지표:
  [2]   claim 추출 행(1건 이상)
  [4+5] coverage + value-recall (T-label gold_figures 기준)
  [6]   Top-1 value-recall (proxy)
  [7]   macro-F1 + recall[T/F/M/N]
  [8]   M-recall · M-precision · M-F1
  [9]   exact-match

저장  : benchmark/e2e/innnn_<YYMMDD>_<NN>.jsonl + .md
실행  : infisical run --env=dev --path=/ -- uv run python benchmark/e2e_hcx_logical_innnn_260622.py
"""
from __future__ import annotations

import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark.reporting import blank_sections, load_ssot, save_result
from benchmark.scoring import (
    prop_row, score_alignment, score_decide_verdict,
    score_verdict_metric,
)
from src.modules.calculate_metric import calculate_metric
from src.modules.check_alignment import check_alignment
from src.modules.decide_verdict import decide_verdict
from src.modules.extract_statistical_claims import extract_statistical_claims
from src.modules.fetch_kosis_data import fetch_kosis_data
from src.modules.generate_explanation import generate_explanation
from src.modules.load_article import load_article
from src.modules.normalize_claim import normalize_claim
from src.modules.rank_evidence import rank_evidence
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.observability import flush, instrument_kosis, set_eval_context, span
from src.schemas.runtime import MasterSchema

_CONCURRENCY = 5
_TOL_ABS = 1.0
_TOL_REL = 0.02
_GOLD_VERDICT = {"T": "T", "F": "F", "M": "M", "NEI": "N"}


def _value_recall(found: float | None, gold_figures: list[dict]) -> bool:
    if found is None:
        return False
    for gf in gold_figures:
        gv = gf.get("value")
        if isinstance(gv, list) or gv is None:
            continue
        if gv == 0:
            if abs(found) <= _TOL_ABS:
                return True
        else:
            if abs(found - gv) <= _TOL_ABS or abs(found / gv - 1) <= _TOL_REL:
                return True
    return False


async def _run_row(row: dict, sem: asyncio.Semaphore) -> list[dict]:
    async with sem:
        label = row["label"]
        gold_figures = row.get("gold_figures") or []
        gold_verdict = _GOLD_VERDICT.get(label, "N")
        in_alignment = label in ("T", "M")
        has_gold = label == "T"

        ms = MasterSchema(content=row["text"])
        error_stage: str | None = None

        with span(f"row:{row['row_id']}", metadata={"label": label, "row_id": row["row_id"]}):
            for step_n, step_name, fn in [
                (1, "load_article", load_article),
                (2, "extract_statistical_claims", extract_statistical_claims),
                (3, "normalize_claim", normalize_claim),
                (4, "retrieve_kosis_candidates", retrieve_kosis_candidates),
                (5, "fetch_kosis_data", fetch_kosis_data),
                (6, "rank_evidence", rank_evidence),
                (7, "calculate_metric", calculate_metric),
                (8, "check_alignment", check_alignment),
                (9, "decide_verdict", decide_verdict),
                (10, "generate_explanation", generate_explanation),
            ]:
                if error_stage:
                    break
                try:
                    with span(f"[{step_n}] {step_name}"):
                        await fn(ms)
                except Exception as e:
                    error_stage = f"[{step_n}] {step_name}: {e}"

        # 중간 출력 수집
        claims = ms.claims or []
        s2_n_claims = len(claims)

        claim_results_map: dict = {}
        if ms.verifications and ms.verifications.claim_results:
            for cr in ms.verifications.claim_results:
                claim_results_map[cr.claim_id] = cr

        records: list[dict] = []
        for ca in (ms.analysis or []):
            evidences = ca.evidences or []
            ev0 = evidences[0] if evidences else None
            found = ev0.value if ev0 else None
            answered = found is not None

            cell_correct = _value_recall(found, gold_figures) if (has_gold and gold_figures) else False
            top1_correct = _value_recall(found, gold_figures) if gold_figures else False

            cr = claim_results_map.get(ca.claim_id)
            pred_verdict = (cr.verdict if cr else None) or "N"
            pred_M = (pred_verdict == "M")
            gold_M = (label == "M")
            match = (pred_verdict == gold_verdict)

            rec: dict = {
                "row_id": row["row_id"],
                "claim_id": ca.claim_id,
                "stage": "e2e",
                "label": label,
                "input": {"text": row["text"][:200]},
                "output": {
                    "s2_n_claims": s2_n_claims,
                    "found_value": found,
                    "tbl_id": ev0.kosis_tbl_id if ev0 else None,
                    "itm_id": ev0.kosis_item_id if ev0 else None,
                    "pred_verdict": pred_verdict,
                },
                "gold": {
                    "gold_figures": gold_figures,
                    "gold_verdict": gold_verdict,
                    "gold_M": gold_M,
                },
                "answered": answered,
                "cell_correct": cell_correct if has_gold else None,
                "has_gold_for_fetch": has_gold,
                "top1_correct": top1_correct if gold_figures else None,
                "gold_verdict": gold_verdict,
                "pred_verdict": pred_verdict,
                "gold_M": gold_M,
                "pred_M": pred_M,
                "in_alignment_set": in_alignment,
                "match": match,
                "error_stage": error_stage,
            }
            records.append(rec)

        if not records:
            records.append({
                "row_id": row["row_id"],
                "claim_id": None,
                "stage": "e2e",
                "label": label,
                "input": {"text": row["text"][:200]},
                "output": {"s2_n_claims": s2_n_claims, "found_value": None,
                           "tbl_id": None, "itm_id": None, "pred_verdict": "N"},
                "gold": {"gold_figures": gold_figures, "gold_verdict": gold_verdict, "gold_M": label == "M"},
                "answered": False,
                "cell_correct": False if has_gold else None,
                "has_gold_for_fetch": has_gold,
                "top1_correct": None,
                "gold_verdict": gold_verdict,
                "pred_verdict": "N",
                "gold_M": label == "M",
                "pred_M": False,
                "in_alignment_set": in_alignment,
                "match": gold_verdict == "N",
                "error_stage": error_stage,
            })

        return records


def _build_metrics(records: list[dict]) -> list[dict]:
    rows: list[dict] = []

    n_rows_with_claims = len(set(
        r["row_id"] for r in records if r.get("output", {}).get("s2_n_claims", 0) > 0
    ))
    n_total_rows = len(set(r["row_id"] for r in records))
    rows.append(prop_row("[2] claim 추출 행(1건 이상)", "coverage", n_rows_with_claims, n_total_rows))

    n_all = len(records)
    answered = [r for r in records if r.get("answered")]
    rows.append(prop_row("[4+5] 조회 성공률(coverage)", "coverage", len(answered), n_all))

    fetch_gold = [r for r in records if r.get("has_gold_for_fetch")]
    fetch_correct = [r for r in fetch_gold if r.get("cell_correct")]
    if fetch_gold:
        rows.append(prop_row("[4+5] value-recall (T-label)", "accuracy",
                             len(fetch_correct), len(fetch_gold)))

    rank_gold = [r for r in records if r.get("top1_correct") is not None]
    if rank_gold:
        rows.append(prop_row("[6] Top-1 value-recall (proxy)", "accuracy",
                             sum(1 for r in rank_gold if r.get("top1_correct")),
                             len(rank_gold)))

    rows += score_verdict_metric(records, labels=["T", "F", "M", "N"])

    alignment_recs = [r for r in records if r.get("in_alignment_set")]
    if alignment_recs:
        rows += score_alignment(alignment_recs)

    rows += score_decide_verdict(records)

    return rows


def _funnel(records: list[dict], n_rows: int) -> str:
    n_claims = sum(1 for r in records if r.get("claim_id"))
    n_answered = sum(1 for r in records if r.get("answered"))
    vc = Counter(r.get("pred_verdict", "N") for r in records)
    err = sum(1 for r in records if r.get("error_stage"))
    return (
        f"| 관문 | 건수 |\n|---|---|\n"
        f"| 입력 row | {n_rows} |\n"
        f"| claim 추출 | {n_claims} |\n"
        f"| evidence 확보(answered) | {n_answered} |\n"
        f"| 오류 발생 claim | {err} |\n"
        f"| 판정 T | {vc.get('T', 0)} |\n"
        f"| 판정 F | {vc.get('F', 0)} |\n"
        f"| 판정 M | {vc.get('M', 0)} |\n"
        f"| 판정 N(NEI) | {vc.get('N', 0)} |\n"
    )


async def main() -> None:
    set_eval_context(
        session_id="e2e-hcx-logical-260622",
        tags=["e2e", "hcx", "logical", "retrieve-fetch"],
        environment="eval",
    )
    instrument_kosis()

    rows = load_ssot()
    from collections import Counter as _C
    ld = _C(r["label"] for r in rows)
    print(f"SSOT {len(rows)}행 (T{ld['T']}/F{ld['F']}/M{ld['M']}/NEI{ld['NEI']}) 로드.", flush=True)

    sem = asyncio.Semaphore(_CONCURRENCY)
    nested = await asyncio.gather(*(_run_row(r, sem) for r in rows))
    records = [rec for sub in nested for rec in sub]

    flush()

    metrics = _build_metrics(records)
    funnel = _funnel(records, len(rows))

    sec = blank_sections()
    sec["개요"] = (
        f"아인님 logical 파이프라인 e2e 평가 (retrieve_kosis_candidates + fetch_kosis_data). "
        f"SSOT {len(rows)}행 (T{ld['T']}/F{ld['F']}/M{ld['M']}/NEI{ld['NEI']}). "
        f"agent 파이프라인(innnn_260622_05)과 직접 비교용."
    )
    sec["테스트 방법"] = (
        f"SSOT 213행 → 1~10단계 전체 파이프라인 (4=retrieve, 5=fetch). "
        f"동시 처리 {_CONCURRENCY}행. "
        f"[5] 허용오차: 절대 {_TOL_ABS} 또는 상대 {_TOL_REL*100:.0f}%(T-label만 채점). "
        f"비교: innnn_260622_05 (agent) vs 이 결과 (logical)."
    )
    sec["분석"] = funnel
    sec["개선 전후 비교"] = "agent vs logical 비교 — 성능 수치 표 참조."
    sec["한계·주의"] = (
        "[4+5] value-recall은 T-label gold_figures 보유 행만. "
        "클래스 불균형(T:123 vs F/M/NEI 각 30) — 신뢰구간 보수 해석."
    )

    jsonl, md = save_result("e2e", "innnn", records, metrics, sec)
    print(f"저장: {jsonl}", flush=True)
    print(f"저장: {md}", flush=True)

    n_ans = sum(1 for r in records if r["answered"])
    n_cor = sum(1 for r in records if r.get("cell_correct"))
    print(f"claim {len(records)}건 | answered {n_ans} | T-label 정답 {n_cor}", flush=True)
    for m in metrics:
        name = m.get("지표") or m.get("지표") or list(m.values())[0]
        val = m.get("값") or m.get("값") or list(m.values())[1]
        print(f"  {name} {val}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
