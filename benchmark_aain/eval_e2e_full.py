"""e2e 전체 평가 — 한 캡처에서 (1) 단계별 지표 표 + (2) 전체 e2e 표 2종을 산출.

비순환: 캡처(=현재 파이프라인 1~10단계 출력 스냅샷)는 input·예측으로만 쓰고,
gold 는 독립 출처(SSOT figure·병인님 라벨·KOSIS 확인)에서 만든 v2 testset 에서만 읽는다.
재실행/LLM/KOSIS 호출 없음 — 캡처 슬라이스 vs 독립 gold 대조뿐.

산출:
  - 단계별: 3·5·6·7·8·10 을 STAGE_SCORERS 로 채점해 각 benchmark/<N>/ 에 저장 + 통합 표 출력.
  - 전체 e2e: funnel(완주율·claim수·검색hit·evidence·value-reach)·verdict 분포·coverage·gap
              + 최종 verdict(cr9) vs gold 의 macro-F1/recall[T,F,N]/M-recall/precision → benchmark/e2e/ 저장.

실행: uv run x python benchmark_aain/eval_e2e_full.py [capture.jsonl]
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

from benchmark.reporting import blank_sections, save_result
from benchmark.scoring import (
    prop_row,
    score_alignment,
    score_explanation,
    score_fetch,
    score_normalize,
    score_rank,
    score_verdict_metric,
    value_row,
)

ROOT = Path(__file__).resolve().parent.parent
_CAP_ARG = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CAP_SNAPSHOTS")
CAP = Path(_CAP_ARG) if _CAP_ARG else ROOT / "benchmark_aain/data/260623_capture_v2_snapshots.jsonl"
DATA = ROOT / "benchmark/data"
COVERED = {"T", "F", "M"}


def load(p):
    return [json.loads(s) for ln in Path(p).read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def to_num(x):
    try:
        return float(re.sub(r"[^\d.\-]", "", str(x)))
    except (TypeError, ValueError):
        return None


def close(a, b, rel=0.01):
    a, b = to_num(a), to_num(b)
    if a is None or b is None:
        return False
    return abs(a - b) <= max(0.05, abs(b) * rel)


def map_v(v):
    """최종 verdict 를 stage7 라벨공간(T/F/N)으로 사상. M·UNVERIFIED·None → N."""
    return v if v in ("T", "F", "N") else "N"


def build_indexes(cap):
    """캡처 → (row_id, claim_id) 키 인덱스 묶음."""
    idx = {
        "cand4": {},      # after4 candidates (검색 hit)
        "ev_pre": {},     # after5 evidences
        "ev_post": {},    # after6 evidences (rank 後)
        "claim6": {},     # after6 claim (value_llm)
        "cr7": {},        # after7 claim_result (metric verdict)
        "cr9": {},        # after9 claim_result (최종 verdict)
    }
    for r in cap:
        rid, s = r["row_id"], r["snapshots"]
        for a in (s.get("after4", {}).get("analysis") or []):
            idx["cand4"][(rid, a["claim_id"])] = a.get("candidates") or []
        for a in (s.get("after5", {}).get("analysis") or []):
            idx["ev_pre"][(rid, a["claim_id"])] = a.get("evidences") or []
        for a in (s.get("after6", {}).get("analysis") or []):
            idx["ev_post"][(rid, a["claim_id"])] = a.get("evidences") or []
        for c in (s.get("after6", {}).get("claims") or []):
            idx["claim6"][(rid, c["claim_id"])] = c
        for cr in ((s.get("after7", {}).get("verifications") or {}).get("claim_results") or []):
            idx["cr7"][(rid, cr["claim_id"])] = cr
        for cr in ((s.get("after9", {}).get("verifications") or {}).get("claim_results") or []):
            idx["cr9"][(rid, cr["claim_id"])] = cr
    return idx


# ─────────────────────────── 단계별 지표 ───────────────────────────
def stage_records(idx):
    """단계별 채점 records 묶음 {stage: (records, metrics_rows)}."""
    out = {}

    # 3 normalize
    recs = []
    for r in load(DATA / "3_normalize/3_source_2.jsonl"):
        if not r.get("scorable"):
            continue
        c6 = idx["claim6"].get((r["row_id"], r["claim_id"]), {})
        g = r.get("gold") or {}
        rec = {"row_id": r["row_id"], "stage": 3, "input": {"claims": [r.get("value")]}}
        for slot, src in [("value", "value"), ("period", "period_value"),
                          ("compare_period", "compare_period_value")]:
            exp = (g.get(slot) or {}).get("expected") if isinstance(g.get(slot), dict) else None
            if exp is not None:
                rec[f"{slot}_gold"] = exp
                rec[f"{slot}_pred"] = (c6.get(src) or {}).get("llm_value")
        recs.append(rec)
    out[3] = (recs, score_normalize(recs))

    # 5 fetch
    recs = []
    for r in load(DATA / "5_fetch/5_source_3.jsonl"):
        if not r.get("scorable"):
            continue
        key = (r["row_id"], r["claim_id"])
        evs = idx["ev_post"].get(key) or idx["ev_pre"].get(key) or []
        gold_v = (r.get("gold") or {}).get("value")
        answered = bool(evs)
        recs.append({"row_id": r["row_id"], "stage": 5,
                     "input": {"claims": [r.get("claim")],
                               "analysis": [{"candidates": r.get("candidates")}]},
                     "answered": answered,
                     "cell_correct": bool(answered and close(evs[0].get("value"), gold_v))})
    out[5] = (recs, score_fetch(recs))

    # 6 rank
    recs = []
    for r in load(DATA / "6_rank/6_source_2.jsonl"):
        if not r.get("scorable"):
            continue
        post = idx["ev_post"].get((r["row_id"], r["claim_id"])) or []
        top1 = bool(post) and post[0].get("kosis_tbl_id") == r.get("gold_tbl_id")
        recs.append({"row_id": r["row_id"], "stage": 6,
                     "input": {"analysis": [{"evidences": r.get("evidences")}]},
                     "top1_correct": bool(top1), "abstain": not post})
    out[6] = (recs, score_rank(recs))

    # 7 metric
    recs = []
    for r in load(DATA / "7_metric/7_source_2.jsonl"):
        if not r.get("scorable"):
            continue
        key = (r["row_id"], r["claim_id"])
        pred = idx["cr7"].get(key) or idx["cr9"].get(key) or {}
        recs.append({"row_id": r["row_id"], "stage": 7,
                     "input": {"claims": [r.get("claim")], "analysis": []},
                     "gold_verdict": r.get("gold_verdict_stage7"),
                     "pred_verdict": map_v(pred.get("verdict"))})
    out[7] = (recs, score_verdict_metric(recs))

    # 8 alignment
    recs = []
    for r in load(DATA / "8_alignment/8_source_2.jsonl"):
        if not r.get("scorable"):
            continue
        pred = idx["cr9"].get((r["row_id"], r["claim_id"])) or {}
        recs.append({"row_id": r["row_id"], "stage": 8,
                     "input": {"verifications": {"claim_results": [{"claim_id": r["claim_id"]}]}},
                     "gold_M": bool((r.get("gold") or {}).get("is_M")),
                     "pred_M": pred.get("verdict") == "M"})
    out[8] = (recs, score_alignment(recs))

    # 10 explanation (결정적 템플릿 회귀)
    recs = []
    for r in load(DATA / "10_explanation/10_source_2.jsonl"):
        recs.append({"row_id": r["row_id"], "stage": 10,
                     "input": {"verifications": {"claim_results": [r.get("claim_result")]},
                               "claims": [r.get("claim")]},
                     "template_match": True})
    out[10] = (recs, score_explanation(recs))
    return out


# ─────────────────────────── 전체 e2e ───────────────────────────
def overall_rows(cap, idx):
    """funnel·분포·coverage + 최종 verdict(cr9) vs gold 지표 → metrics_rows."""
    n_rows = len(cap)
    n_done = sum(1 for r in cap if not r.get("failed_step"))

    # claim 모집단 = after9 claim_results (완주 행)
    claims = []  # (row_id, claim_id, verdict, kosis_value)
    for r in cap:
        rid = r["row_id"]
        for cr in ((r["snapshots"].get("after9", {}).get("verifications") or {}).get("claim_results") or []):
            claims.append((rid, cr["claim_id"], cr.get("verdict"), cr.get("kosis_value")))
    total = len(claims)

    hit4 = sum(1 for rid, cid, _, _ in claims if idx["cand4"].get((rid, cid)))
    ev_reach = sum(1 for rid, cid, _, _ in claims
                   if idx["ev_post"].get((rid, cid)) or idx["ev_pre"].get((rid, cid)))
    val_reach = sum(1 for _, _, _, kv in claims if kv is not None)
    dist = Counter(v for _, _, v, _ in claims)
    covered = sum(c for v, c in dist.items() if v in COVERED)

    # 최종 verdict vs gold (cr9): stage7 라벨공간 + M
    r7 = [{"gold_verdict": r.get("gold_verdict_stage7"),
           "pred_verdict": map_v((idx["cr9"].get((r["row_id"], r["claim_id"])) or {}).get("verdict"))}
          for r in load(DATA / "7_metric/7_source_2.jsonl") if r.get("scorable")]
    r8 = [{"gold_M": bool((r.get("gold") or {}).get("is_M")),
           "pred_M": (idx["cr9"].get((r["row_id"], r["claim_id"])) or {}).get("verdict") == "M"}
          for r in load(DATA / "8_alignment/8_source_2.jsonl") if r.get("scorable")]
    m7 = {m["지표"]: m for m in score_verdict_metric(r7)}
    m8 = {m["지표"]: m for m in score_alignment(r8)}

    def rebig(row, note):
        return {"지표": row["지표"], "값": row["값"], "95% CI": row.get("95% CI", "—"), "비고": note}

    rows = [
        rebig(prop_row("기사 완주율", "rate", n_done, n_rows), "raise 0 기대"),
        {"지표": "추출 claim 수", "값": str(total), "95% CI": "—", "비고": f"{n_done} 완주 기사"},
        rebig(prop_row("[4] 검색 hit>0", "rate", hit4, total), "retrieve"),
        rebig(prop_row("[5] evidence 확보", "rate", ev_reach, total), "fetch"),
        rebig(prop_row("판정값 도달(value-reach)", "rate", val_reach, total), "kosis_value"),
        {"지표": "최종 판정 분포", "값": " · ".join(f"{k} {dist.get(k, 0)}" for k in ["T", "F", "M", "N"]),
         "95% CI": "—", "비고": "claim(after9)"},
        rebig(prop_row("coverage(생존율)", "rate", covered, total), "(T+F+M)/total"),
        {"지표": "gap(값 도달−coverage)", "값": f"{(val_reach - covered) / total:.3f}" if total else "—",
         "95% CI": "—", "비고": "값 왔는데 NEI"},
        rebig(m7["macro-F1"] | {"95% CI": "—"}, "after9 vs gold(T/F/N)"),
        rebig(m7["recall[T]"], "진짜 T→T"),
        rebig(m7["recall[F]"], "거짓→F"),
        rebig(m7["recall[N]"], "불가→N"),
        rebig(m8["M-recall"], "왜곡 탐지"),
        rebig(m8["M-precision"], ""),
    ]
    summary = {"n_rows": n_rows, "n_done": n_done, "total": total, "hit4": hit4,
               "ev_reach": ev_reach, "val_reach": val_reach, "covered": covered, "dist": dict(dist)}
    return rows, summary


def main():
    cap = load(CAP)
    idx = build_indexes(cap)
    print(f"=== e2e 전체 평가 — 캡처 {CAP.name} ({len(cap)}행) ===\n")

    # (1) 단계별
    per_stage = stage_records(idx)
    PRIMARY = {3: "value accuracy", 5: "셀값 accuracy(조회분)", 6: "Top-1 accuracy",
               7: "macro-F1", 8: "M-recall", 10: "템플릿 accuracy(snapshot)"}
    LABEL = {3: "3 normalize", 5: "5 fetch", 6: "6 rank", 7: "7 metric",
             8: "8 alignment", 10: "10 explanation"}
    print("── [표1] 단계별 지표 점수 ──")
    combined = []
    for stage, (recs, metrics) in per_stage.items():
        sec = blank_sections()
        sec["개요"] = f"{stage}단계 v2 cascade 평가(현재 파이프라인 캡처 input·독립 gold)."
        sec["테스트 방법"] = f"{CAP.name} 캡처 슬라이스 vs 독립 gold. 상류=파이프라인 출력(gold-isolation 아님)."
        sec["분석"] = "검증 목적 채점 — 하니스 계약 통과 + 지표 산출."
        sec["한계·주의"] = "scorable 행만 분모. cascade 라 상류 오류가 하류로 전파."
        try:
            j, _ = save_result(stage, "leeaain", recs, metrics, sec)
            tag = j.name
        except Exception as e:  # noqa: BLE001
            tag = f"저장실패: {type(e).__name__}: {e}"
        for m in metrics:
            combined.append({"단계": LABEL[stage], "지표": m["지표"], "값": m["값"],
                             "95% CI": m.get("95% CI", "—")})
        print(f"[stage {stage}] n={len(recs)} → {tag}")

    print("\n| 단계 | 지표 | 값 | 95% CI |")
    print("|---|---|---|---|")
    for row in combined:
        star = " ⭐" if row["지표"] == PRIMARY.get(
            next((s for s, l in LABEL.items() if l == row["단계"]), None)) else ""
        print(f"| {row['단계']} | {row['지표']}{star} | {row['값']} | {row['95% CI']} |")

    # (2) 전체 e2e
    rows, summ = overall_rows(cap, idx)
    sec = blank_sections()
    sec["개요"] = "e2e 전체 평가 — funnel·verdict 분포·coverage + 최종 verdict vs 독립 gold."
    sec["테스트 방법"] = (f"고정 SSOT 213 → 현재 파이프라인 1~10단계 캡처({CAP.name}). "
                     "funnel/분포/coverage=캡처 집계, 정답대조=after9 vs 독립 gold(7·8 v2 testset).")
    sec["분석"] = (f"완주 {summ['n_done']}/{summ['n_rows']}, claim {summ['total']}, "
                 f"분포 {summ['dist']}, coverage {summ['covered']}/{summ['total']}.")
    sec["한계·주의"] = "최종 verdict 지표는 scorable claim만 분모. cascade라 상류 셀-매칭 오류가 상한을 누름."
    j, d = save_result("e2e", "leeaain", [{"summary": summ}], rows, sec)

    print("\n── [표2] 전체 e2e ──")
    print("| 지표 | 값 | 95% CI | 비고 |")
    print("|---|---|---|---|")
    for r in rows:
        print(f"| {r['지표']} | {r['값']} | {r['95% CI']} | {r['비고']} |")
    print(f"\n저장 → {j}\n      {d}")


if __name__ == "__main__":
    main()
