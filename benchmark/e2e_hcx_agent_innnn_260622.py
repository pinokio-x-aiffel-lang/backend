"""E2E 벤치마크: HCX-007 Think + HCX-005 Act, 아인님 모듈 통합 + Langfuse 트레이싱.

입력  : SSOT 213행 (T123/F30/M30/NEI30)
파이프라인 : 1→2→3→[4+5 agent: HCX-007+HCX-005]→6→7→8→9→10
트레이싱 : Langfuse row별 root span + 단계 span + KOSIS HTTP span

측정 지표:
  [2]   claim 추출 수 (P/R/F1 → eval_stage2.py 별도 실행 필요)
  [3]   normalize 중간값 저장 (accuracy → eval_stage3.py 별도 실행 필요)
  [4+5] coverage + value-recall (T-label gold_figures 기준)
  [6]   Top-1 value-recall (proxy: evidences[0].value ≈ gold_figures)
  [7]   macro-F1 + recall[T/F/M/N]
  [8]   M-recall · M-precision · M-F1
  [9]   exact-match (pred_verdict == gold_verdict)

저장  : benchmark/e2e/innnn_<YYMMDD>_<NN>.jsonl + .md
실행  : infisical run -- uv run python benchmark/e2e_hcx_agent_innnn_260622.py
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
    score_fetch, score_rank, score_verdict_metric, value_row,
)
from src.llm.model_presets import MAP_CLAIM_ACT, MAP_CLAIM_THINK
from src.modules.calculate_metric import calculate_metric
from src.modules.check_alignment import check_alignment
from src.modules.decide_verdict import decide_verdict
from src.modules.extract_statistical_claims import extract_statistical_claims
from src.modules.generate_explanation import generate_explanation
from src.modules.load_article import load_article
from src.modules.map_claim_via_agent import map_claim_via_agent
from src.modules.normalize_claim import normalize_claim
from src.modules.rank_evidence import rank_evidence
from src.observability import flush, instrument_kosis, set_eval_context, span
from src.schemas.runtime import MasterSchema

_CONCURRENCY = 5
_TOL_ABS = 1.0
_TOL_REL = 0.02
_GOLD_VERDICT = {"T": "T", "F": "F", "M": "M", "NEI": "N"}


# ── 채점 헬퍼 ─────────────────────────────────────────────────────────────────

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


# ── row 실행 ─────────────────────────────────────────────────────────────────

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
            # [1] load_article
            try:
                with span("[1] load_article"):
                    await load_article(ms)
            except Exception as e:
                error_stage = f"[1] load_article: {e}"

            # [2] extract_statistical_claims
            if not error_stage:
                try:
                    with span("[2] extract_statistical_claims"):
                        await extract_statistical_claims(ms)
                except Exception as e:
                    error_stage = f"[2] extract_statistical_claims: {e}"

            # [3] normalize_claim
            if not error_stage:
                try:
                    with span("[3] normalize_claim"):
                        await normalize_claim(ms)
                except Exception as e:
                    error_stage = f"[3] normalize_claim: {e}"

            # [4+5] map_claim_via_agent (HCX-007 Think + HCX-005 Act)
            if not error_stage:
                try:
                    with span("[4+5] map_claim_via_agent"):
                        await map_claim_via_agent(
                            ms,
                            think_preset=MAP_CLAIM_THINK,
                            act_preset=MAP_CLAIM_ACT,
                        )
                except Exception as e:
                    error_stage = f"[4+5] map_claim_via_agent: {e}"

            # [6] rank_evidence
            if not error_stage:
                try:
                    with span("[6] rank_evidence"):
                        await rank_evidence(ms)
                except Exception as e:
                    error_stage = f"[6] rank_evidence: {e}"

            # [7] calculate_metric
            if not error_stage:
                try:
                    with span("[7] calculate_metric"):
                        await calculate_metric(ms)
                except Exception as e:
                    error_stage = f"[7] calculate_metric: {e}"

            # [8] check_alignment
            if not error_stage:
                try:
                    with span("[8] check_alignment"):
                        await check_alignment(ms)
                except Exception as e:
                    error_stage = f"[8] check_alignment: {e}"

            # [9] decide_verdict
            if not error_stage:
                try:
                    with span("[9] decide_verdict"):
                        await decide_verdict(ms)
                except Exception as e:
                    error_stage = f"[9] decide_verdict: {e}"

            # [10] generate_explanation
            if not error_stage:
                try:
                    with span("[10] generate_explanation"):
                        await generate_explanation(ms)
                except Exception as e:
                    error_stage = f"[10] generate_explanation: {e}"

        # ── 중간 출력 수집 ───────────────────────────────────────────────────

        # [2] claim 추출 결과
        claims = ms.claims or []
        s2_n_claims = len(claims)
        s2_claim_types = [
            (c.claim_type.value if hasattr(c.claim_type, "value") else str(c.claim_type))
            for c in claims
        ]

        # [3] normalize 결과
        s3_values = [c.value.llm_value for c in claims]
        s3_periods = [c.period_value.llm_value for c in claims]

        # [4+5] evidence 결과 (analysis 기반)
        claim_results_map: dict = {}
        if ms.verifications and ms.verifications.claim_results:
            for cr in ms.verifications.claim_results:
                claim_results_map[cr.claim_id] = cr

        by_claim_id = {c.claim_id: c for c in claims}

        records: list[dict] = []
        for ca in (ms.analysis or []):
            claim = by_claim_id.get(ca.claim_id)

            # [4+5] evidence
            evidences = ca.evidences or []
            ev0 = evidences[0] if evidences else None
            found = ev0.value if ev0 else None
            answered = found is not None

            # [4+5] 채점
            cell_correct = _value_recall(found, gold_figures) if (has_gold and gold_figures) else False

            # [6] Top-1 value-recall proxy
            top1_correct = _value_recall(found, gold_figures) if gold_figures else False

            # [7~9] verdict
            cr = claim_results_map.get(ca.claim_id)
            pred_verdict = (cr.verdict if cr else None) or "N"
            pred_M = (pred_verdict == "M")
            gold_M = (label == "M")
            match = (pred_verdict == gold_verdict)

            # normalize 중간값 (claim 매핑)
            claim_value_normalized = claim.value.llm_value if claim else None
            claim_period_normalized = claim.period_value.llm_value if claim else None

            rec: dict = {
                "row_id": row["row_id"],
                "claim_id": ca.claim_id,
                "stage": "e2e",
                "label": label,
                # ── 입력 ──
                "input": {"text": row["text"][:200]},
                # ── 중간 출력 ──
                "output": {
                    "s2_n_claims": s2_n_claims,
                    "s2_claim_types": s2_claim_types,
                    "s3_value_normalized": claim_value_normalized,
                    "s3_period_normalized": claim_period_normalized,
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
                # ── 채점 필드 ──
                # [4+5]
                "answered": answered,
                "cell_correct": cell_correct if has_gold else None,
                "has_gold_for_fetch": has_gold,
                # [6]
                "top1_correct": top1_correct if gold_figures else None,
                # [7]
                "gold_verdict": gold_verdict,
                "pred_verdict": pred_verdict,
                # [8]
                "gold_M": gold_M,
                "pred_M": pred_M,
                "in_alignment_set": in_alignment,
                # [9]
                "match": match,
                # 메타
                "error_stage": error_stage,
            }
            records.append(rec)

        # claim 0건 row → placeholder
        # s2_n_claims는 실제 추출 수 사용 — 4+5 에러로 ms.analysis가 비어도
        # 2단계가 성공했으면 올바르게 반영되어야 함.
        if not records:
            records.append({
                "row_id": row["row_id"],
                "claim_id": None,
                "stage": "e2e",
                "label": label,
                "input": {"text": row["text"][:200]},
                "output": {
                    "s2_n_claims": s2_n_claims,
                    "s2_claim_types": s2_claim_types,
                    "s3_value_normalized": None,
                    "s3_period_normalized": None,
                    "found_value": None,
                    "tbl_id": None,
                    "itm_id": None,
                    "pred_verdict": "N",
                },
                "gold": {
                    "gold_figures": gold_figures,
                    "gold_verdict": gold_verdict,
                    "gold_M": label == "M",
                },
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


# ── 지표 빌드 ─────────────────────────────────────────────────────────────────

def _build_metrics(records: list[dict]) -> list[dict]:
    rows: list[dict] = []

    # [2] claim 추출 수 (참고용)
    n_rows_with_claims = len(set(
        r["row_id"] for r in records if r.get("output", {}).get("s2_n_claims", 0) > 0
    ))
    n_total_rows = len(set(r["row_id"] for r in records))
    rows.append(prop_row("[2] claim 추출 행(1건 이상)", "coverage",
                         n_rows_with_claims, n_total_rows))

    # [4+5] coverage + value-recall
    n_all = len(records)
    answered = [r for r in records if r.get("answered")]
    rows.append(prop_row("[4+5] 조회 성공률(coverage)", "coverage", len(answered), n_all))

    fetch_gold = [r for r in records if r.get("has_gold_for_fetch")]
    fetch_correct = [r for r in fetch_gold if r.get("cell_correct")]
    if fetch_gold:
        rows.append(prop_row("[4+5] value-recall (T-label)", "accuracy",
                             len(fetch_correct), len(fetch_gold)))

    # [6] Top-1 value-recall proxy
    rank_gold = [r for r in records if r.get("top1_correct") is not None]
    if rank_gold:
        rows.append(prop_row("[6] Top-1 value-recall (proxy)", "accuracy",
                             sum(1 for r in rank_gold if r.get("top1_correct")),
                             len(rank_gold)))

    # [7] macro-F1 + recall[T/F/M/N]
    rows += score_verdict_metric(records, labels=["T", "F", "M", "N"])

    # [8] M-recall · M-precision · M-F1
    alignment_recs = [r for r in records if r.get("in_alignment_set")]
    if alignment_recs:
        rows += score_alignment(alignment_recs)

    # [9] exact-match
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


# ── main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    set_eval_context(
        session_id="e2e-hcx-agent-260622",
        tags=["e2e", "hcx", "hcx-007-think", "hcx-005-act"],
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
        f"HCX-007 Think + HCX-005 Act, 아인님 2·3·6~10단계 통합 e2e 파이프라인 평가. "
        f"SSOT {len(rows)}행 (T{ld['T']}/F{ld['F']}/M{ld['M']}/NEI{ld['NEI']}). "
        f"[4+5]: map_claim_via_agent (HCX-007 think:low → HCX-005 FC). "
        f"Langfuse 트레이싱: row별 root span + 단계 span + KOSIS HTTP span."
    )
    sec["테스트 방법"] = (
        f"SSOT 213행 → 1~10단계 전체 파이프라인. "
        f"동시 처리 {_CONCURRENCY}행. "
        f"[5] 허용오차: 절대 {_TOL_ABS} 또는 상대 {_TOL_REL*100:.0f}%(T-label만 채점). "
        f"[6] Top-1 value-recall = evidences[0].value ≈ gold_figures(proxy). "
        f"[7] gold 매핑: T→T, F→F, M→M, NEI→N. "
        f"[2][3] P/R/F1·accuracy: eval_stage2.py / eval_stage3.py 별도 실행 필요."
    )
    sec["분석"] = funnel
    sec["개선 전후 비교"] = "_(작성 필요)_"
    sec["한계·주의"] = (
        "[4+5] value-recall은 T-label gold_figures 보유 행만. "
        "[6] Top-1은 agent가 반환한 evidences[0] 단일 값 기준(rank 의미 없음). "
        "[2][3] cascade 측정이라 상류 오류 섞임. "
        "클래스 불균형(T:123 vs F/M/NEI 각 30) — 신뢰구간 보수 해석."
    )

    jsonl, md = save_result("e2e", "innnn", records, metrics, sec)
    print(f"저장: {jsonl}", flush=True)
    print(f"저장: {md}", flush=True)

    n_ans = sum(1 for r in records if r["answered"])
    n_cor = sum(1 for r in records if r.get("cell_correct"))
    print(f"claim {len(records)}건 | answered {n_ans} | T-label 정답 {n_cor}", flush=True)
    print("지표:", flush=True)
    for m in metrics:
        print(f"  {m['지표']} {m['값']} {m.get('95% CI','')}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
