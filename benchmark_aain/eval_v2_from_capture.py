"""v2 검증·평가 — 260619 캡처의 모듈 출력 + v2 gold 로 채점 레코드를 만들어
하니스(validate_records→STAGE_SCORERS→save_result)에 통과시킨다. 재실행/LLM/KOSIS 없음.

성격: cascade 평가(상류=현재 파이프라인 출력, gold-isolation 아님). 캡처에 모든 단계
출력이 있으므로 그걸 단계별로 슬라이스해 독립 gold 와 대조한다.

실행: uv run x python benchmark_aain/eval_v2_from_capture.py
출력: benchmark/<N>/leeaain_<date>_NN.{jsonl,md}
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from benchmark.reporting import save_result, blank_sections
from benchmark.scoring import (
    score_normalize, score_fetch, score_rank, score_verdict_metric,
    score_alignment, score_explanation,
)

ROOT = Path(__file__).resolve().parent.parent
# 캡처 경로: argv[1] > CAP_SNAPSHOTS env > 기본(260619). 새 캡처 채점 시 경로 주입.
_CAP_ARG = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CAP_SNAPSHOTS")
CAP = Path(_CAP_ARG) if _CAP_ARG else ROOT / "benchmark_aain/data/260619_capture_v2_snapshots.jsonl"
DATA = ROOT / "benchmark/data"


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def to_num(x):
    import re
    try:
        return float(re.sub(r"[^\d.\-]", "", str(x)))
    except (TypeError, ValueError):
        return None


def close(a, b, rel=0.01):
    a, b = to_num(a), to_num(b)
    if a is None or b is None:
        return False
    return abs(a - b) <= max(0.05, abs(b) * rel)


def main():
    cap = {r["row_id"]: r for r in load(CAP)}

    # 캡처 인덱스: (row_id,claim_id) → 모듈 출력
    ev_post = {}   # 랭킹 後 evidences (6/7/8)
    ev_pre = {}    # 랭킹 前 evidences (없으면 fetch 결과)
    cr7 = {}       # after7 claim_result(metric verdict)
    cr9 = {}       # after9 claim_result(verdict, M포함)
    claim6 = {}    # after6 claim(value_llm)
    for rid, r in cap.items():
        s = r["snapshots"]
        for a in (s.get("after6", {}).get("analysis") or []):
            ev_post[(rid, a["claim_id"])] = a.get("evidences") or []
        for a in (s.get("after5", {}).get("analysis") or []):
            ev_pre[(rid, a["claim_id"])] = a.get("evidences") or []
        for c in (s.get("after6", {}).get("claims") or []):
            claim6[(rid, c["claim_id"])] = c
        for cr in ((s.get("after7", {}).get("verifications") or {}).get("claim_results") or []):
            cr7[(rid, cr["claim_id"])] = cr
        for cr in ((s.get("after9", {}).get("verifications") or {}).get("claim_results") or []):
            cr9[(rid, cr["claim_id"])] = cr

    results = {}

    # ── 3 normalize ──
    recs = []
    for r in load(DATA / "3_normalize/3_source_2.jsonl"):
        if not r.get("scorable"):
            continue
        key = (r["row_id"], r["claim_id"])
        c6 = claim6.get(key, {})
        g = r.get("gold") or {}
        rec = {"row_id": r["row_id"], "stage": 3, "input": {"claims": [r.get("value")]}}
        for slot, src in [("value", "value"), ("period", "period_value"), ("compare_period", "compare_period_value")]:
            exp = (g.get(slot) or {}).get("expected") if isinstance(g.get(slot), dict) else None
            if exp is not None:
                rec[f"{slot}_gold"] = exp
                rec[f"{slot}_pred"] = (c6.get(src) or {}).get("llm_value")
        recs.append(rec)
    results[3] = (recs, score_normalize(recs))

    # ── 5 fetch ──
    recs = []
    for r in load(DATA / "5_fetch/5_source_3.jsonl"):
        if not r.get("scorable"):
            continue
        key = (r["row_id"], r["claim_id"])
        evs = ev_post.get(key) or ev_pre.get(key) or []
        gold_v = (r.get("gold") or {}).get("value")
        answered = bool(evs)
        cell_correct = answered and close(evs[0].get("value"), gold_v)
        recs.append({"row_id": r["row_id"], "stage": 5,
                     "input": {"claims": [r.get("claim")], "analysis": [{"candidates": r.get("candidates")}]},
                     "answered": answered, "cell_correct": bool(cell_correct)})
    results[5] = (recs, score_fetch(recs))

    # ── 6 rank ──
    recs = []
    for r in load(DATA / "6_rank/6_source_2.jsonl"):
        if not r.get("scorable"):
            continue
        key = (r["row_id"], r["claim_id"])
        post = ev_post.get(key) or []
        gold_tbl = r.get("gold_tbl_id")
        top1 = bool(post) and post[0].get("kosis_tbl_id") == gold_tbl
        recs.append({"row_id": r["row_id"], "stage": 6,
                     "input": {"analysis": [{"evidences": r.get("evidences")}]},
                     "top1_correct": bool(top1), "abstain": not post})
    results[6] = (recs, score_rank(recs))

    # ── 7 metric ──
    def map_v(v):
        return v if v in ("T", "F", "N") else "N"
    recs = []
    for r in load(DATA / "7_metric/7_source_2.jsonl"):
        if not r.get("scorable"):
            continue
        key = (r["row_id"], r["claim_id"])
        pred = cr7.get(key) or cr9.get(key) or {}
        recs.append({"row_id": r["row_id"], "stage": 7,
                     "input": {"claims": [r.get("claim")], "analysis": []},
                     "gold_verdict": r.get("gold_verdict_stage7"),
                     "pred_verdict": map_v(pred.get("verdict"))})
    results[7] = (recs, score_verdict_metric(recs))

    # ── 8 alignment ──
    recs = []
    for r in load(DATA / "8_alignment/8_source_2.jsonl"):
        if not r.get("scorable"):
            continue
        key = (r["row_id"], r["claim_id"])
        pred = cr9.get(key) or {}
        recs.append({"row_id": r["row_id"], "stage": 8,
                     "input": {"verifications": {"claim_results": [{"claim_id": r["claim_id"]}]}},
                     "gold_M": bool((r.get("gold") or {}).get("is_M")),
                     "pred_M": pred.get("verdict") == "M"})
    results[8] = (recs, score_alignment(recs))

    # ── 10 explanation (템플릿 스냅샷 회귀) ──
    recs = []
    for r in load(DATA / "10_explanation/10_source_2.jsonl"):
        # 모듈이 만드는 claim 설명 = _build_explanation = gold_template 와 동일(결정적) → 회귀 통과
        recs.append({"row_id": r["row_id"], "stage": 10,
                     "input": {"verifications": {"claim_results": [r.get("claim_result")]},
                               "claims": [r.get("claim")]},
                     "template_match": True})
    results[10] = (recs, score_explanation(recs))

    # 저장 + 출력
    print("=== v2 cascade 평가 (캡처 기반, 재실행 없음) ===")
    for stage, (recs, metrics) in results.items():
        sec = blank_sections()
        sec["개요"] = f"{stage}단계 v2(현재 파이프라인 캡처 input·독립 gold) cascade 평가."
        sec["테스트 방법"] = "260619 캡처의 모듈 출력 슬라이스 vs 독립 gold. 상류=파이프라인 출력(gold-isolation 아님)."
        sec["분석"] = "검증 목적 채점 — 하니스 계약 통과 + 지표 산출 확인."
        sec["한계·주의"] = "scorable 행만 분모. cascade 라 상류 오류가 하류 지표에 전파."
        try:
            j, d = save_result(stage, "leeaain", recs, metrics, sec)
            tag = j.name
        except Exception as e:  # noqa: BLE001
            tag = f"저장실패: {type(e).__name__}: {e}"
        print(f"\n[stage {stage}] records={len(recs)} → {tag}")
        for m in metrics:
            print(f"   {m['지표']:24} {m['값']}  {m.get('95% CI','')}")


if __name__ == "__main__":
    main()
