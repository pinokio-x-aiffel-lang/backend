"""성능 평가 채점기 — 순수 함수(외부 의존성 없음).

primitives  : prf1 · accuracy · recall_at_k · mrr · per_class · macro_f1 · confusion · wilson_ci · mcnemar
stage scorers: score_extract(2) · score_normalize(3) · score_retrieve(4) · score_fetch(5) · score_rank(6) ·
               score_verdict_metric(7) · score_alignment(8) · score_decide_verdict(9) · score_explanation(10)

각 stage scorer 는 records(list[dict])를 받아 **metrics_rows** 를 돌려준다.
metrics_rows 표준 형식(harness.render_md 가 md 표로 렌더):
    [{"지표": str, "종류": str, "값": str, "95% CI": str}, ...]
각 scorer 의 docstring 에 records 가 가져야 하는 필드를 명시한다.
"""
from __future__ import annotations

import math

# --------------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------------- #
def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """이항비율 k/n 의 Wilson 95% 신뢰구간. 작은 표본(n=30)에서 정규근사보다 안전."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((center - margin) / denom, (center + margin) / denom)


def prf1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


def accuracy(correct: int, total: int) -> float:
    return correct / total if total else 0.0


def recall_at_k(gold_ranks: list, k: int) -> tuple[int, int]:
    """gold_ranks: 각 샘플의 정답 1-based 순위(없으면 None). 반환 (hit, n)."""
    n = len(gold_ranks)
    hit = sum(1 for r in gold_ranks if r is not None and r <= k)
    return hit, n


def mrr(gold_ranks: list) -> float:
    n = len(gold_ranks)
    s = sum(1.0 / r for r in gold_ranks if r)
    return s / n if n else 0.0


def per_class(y_true: list, y_pred: list, labels: list) -> dict:
    out = {}
    for lab in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p == lab)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != lab and p == lab)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p != lab)
        pr, rc, f1 = prf1(tp, fp, fn)
        out[lab] = {"precision": pr, "recall": rc, "f1": f1,
                    "support": sum(1 for t in y_true if t == lab), "tp": tp, "fp": fp, "fn": fn}
    return out


def macro_f1(y_true: list, y_pred: list, labels: list) -> float:
    pc = per_class(y_true, y_pred, labels)
    f1s = [pc[l]["f1"] for l in labels]
    return sum(f1s) / len(f1s) if f1s else 0.0


def confusion(y_true: list, y_pred: list, labels: list) -> list:
    idx = {l: i for i, l in enumerate(labels)}
    m = [[0] * len(labels) for _ in labels]
    for t, p in zip(y_true, y_pred):
        if t in idx and p in idx:
            m[idx[t]][idx[p]] += 1
    return m


def confusion_md(y_true: list, y_pred: list, labels: list) -> str:
    """혼동행렬 markdown(분석 섹션에 삽입용). 행=true, 열=pred."""
    m = confusion(y_true, y_pred, labels)
    head = "| true \\ pred | " + " | ".join(labels) + " |"
    sep = "|---|" + "|".join(["---"] * len(labels)) + "|"
    body = [f"| **{labels[i]}** | " + " | ".join(str(m[i][j]) for j in range(len(labels))) + " |"
            for i in range(len(labels))]
    return "\n".join([head, sep, *body])


def mcnemar(before_correct: list, after_correct: list) -> dict:
    """paired 전후 비교(같은 샘플 순서의 bool 리스트). 연속성보정 χ²(1).
    b=개선전✓→후✗(퇴행), c=전✗→후✓(개선). chi2>3.84 면 5% 유의."""
    b = sum(1 for x, y in zip(before_correct, after_correct) if x and not y)
    c = sum(1 for x, y in zip(before_correct, after_correct) if (not x) and y)
    chi2 = ((abs(b - c) - 1) ** 2) / (b + c) if (b + c) else 0.0
    return {"b_regressed": b, "c_improved": c, "chi2": chi2, "significant_5pct": chi2 > 3.84}


# --------------------------------------------------------------------------- #
# row 헬퍼
# --------------------------------------------------------------------------- #
def _f(x: float, nd: int = 3) -> str:
    return f"{x:.{nd}f}"


def prop_row(name: str, kind: str, k: int, n: int) -> dict:
    """비율 지표 한 줄 + Wilson CI."""
    lo, hi = wilson_ci(k, n)
    val = _f(k / n) if n else "—"
    return {"지표": name, "종류": kind, "값": f"{val} ({k}/{n})", "95% CI": f"[{_f(lo)}, {_f(hi)}]"}


def value_row(name: str, kind: str, value) -> dict:
    """CI 없는 스칼라 지표 한 줄(MRR·Δ·F1 등)."""
    v = _f(value) if isinstance(value, float) else str(value)
    return {"지표": name, "종류": kind, "값": v, "95% CI": "—"}


# --------------------------------------------------------------------------- #
# stage scorers
# --------------------------------------------------------------------------- #
def score_extract(records: list) -> list:
    """[2] 문장 P/R/F1 + claim_type 정확도.
    record: gold_claim(bool), pred_claim(bool), [ctype_gold, ctype_pred]."""
    tp = fp = fn = 0
    for r in records:
        g, p = bool(r.get("gold_claim")), bool(r.get("pred_claim"))
        if g and p: tp += 1
        elif p and not g: fp += 1
        elif g and not p: fn += 1
    _, _, f = prf1(tp, fp, fn)
    rows = [prop_row("문장 Precision", "precision", tp, tp + fp),
            prop_row("문장 Recall", "recall", tp, tp + fn),
            value_row("문장 F1", "f1", f)]
    ct = [(r["ctype_gold"], r["ctype_pred"]) for r in records
          if r.get("ctype_gold") is not None and r.get("ctype_pred") is not None]
    if ct:
        yt, yp = [a for a, _ in ct], [b for _, b in ct]
        labs = sorted(set(yt) | set(yp))
        rows.append(prop_row("claim_type accuracy", "accuracy", sum(1 for a, b in ct if a == b), len(ct)))
        rows.append(value_row("claim_type macro-F1", "macro-f1", macro_f1(yt, yp, labs)))
    return rows


def score_normalize(records: list) -> list:
    """[3] value·period·compare_period accuracy(각 분리) + 룰 커버리지.
    record: <slot>_gold, <slot>_pred (slot ∈ value/period/compare_period), [by_rule(bool)]."""
    rows = []
    for slot, label in [("value", "value accuracy"), ("period", "period accuracy"),
                        ("compare_period", "compare_period accuracy")]:
        items = [(r.get(f"{slot}_gold"), r.get(f"{slot}_pred")) for r in records
                 if r.get(f"{slot}_gold") not in (None, "")]
        if items:
            rows.append(prop_row(label, "accuracy", sum(1 for g, p in items if str(g) == str(p)), len(items)))
    cov = [r for r in records if "by_rule" in r]
    if cov:
        rows.append(prop_row("룰 커버리지", "coverage", sum(1 for r in cov if r["by_rule"]), len(cov)))
    return rows


def score_retrieve(records: list, ns=(1, 3, 10)) -> list:
    """[4] Recall@N · MRR · 검색 실패율.
    record: gold_rank(int|None), [success(bool)]."""
    ranks = [r.get("gold_rank") for r in records]
    rows = []
    for k in ns:
        hit, n = recall_at_k(ranks, k)
        rows.append(prop_row(f"Recall@{k}", "recall", hit, n))
    rows.append(value_row("MRR", "mrr", mrr(ranks)))
    succ = [r for r in records if "success" in r]
    if succ:
        rows.append(prop_row("검색 실패율", "fail-rate", sum(1 for r in succ if not r["success"]), len(succ)))
    return rows


def score_fetch(records: list) -> list:
    """[5] 셀값 accuracy × coverage + itmId/population/시점 매칭률.
    record: answered(bool), cell_correct(bool, answered일 때), [itm_match/pop_match/period_match(bool)]."""
    n = len(records)
    answered = [r for r in records if r.get("answered")]
    rows = [prop_row("조회 성공률(coverage)", "coverage", len(answered), n),
            prop_row("셀값 accuracy(조회분)", "accuracy", sum(1 for r in answered if r.get("cell_correct")), len(answered))]
    for key, label in [("itm_match", "itmId 매칭률"), ("pop_match", "population 매칭률"), ("period_match", "시점 매칭률")]:
        items = [r for r in records if key in r]
        if items:
            rows.append(prop_row(label, "match-rate", sum(1 for r in items if r[key]), len(items)))
    return rows


def score_rank(records: list) -> list:
    """[6] Top-1 accuracy · 기권율 · Δ vs RANK 베이스라인.
    record: top1_correct(bool), [abstain(bool)], [baseline_top1_correct(bool)]."""
    n = len(records)
    rows = [prop_row("Top-1 accuracy", "accuracy", sum(1 for r in records if r.get("top1_correct")), n),
            prop_row("기권율", "abstain-rate", sum(1 for r in records if r.get("abstain")), n)]
    base = [r for r in records if "baseline_top1_correct" in r]
    if base:
        a = accuracy(sum(1 for r in base if r.get("top1_correct")), len(base))
        b = accuracy(sum(1 for r in base if r["baseline_top1_correct"]), len(base))
        rows.append(value_row("Δ vs RANK 베이스라인", "delta", a - b))
    return rows


def score_verdict_metric(records: list, labels=("T", "F", "N")) -> list:
    """[7] macro-F1 + 클래스별 recall + mismatch_type accuracy. (혼동행렬은 confusion_md 로 분석 섹션에)
    record: gold_verdict, pred_verdict ∈ labels, [mismatch_gold, mismatch_pred]."""
    labels = list(labels)
    pairs = [(r["gold_verdict"], r["pred_verdict"]) for r in records
             if "gold_verdict" in r and "pred_verdict" in r]
    yt, yp = [a for a, _ in pairs], [b for _, b in pairs]
    rows = [value_row("macro-F1", "macro-f1", macro_f1(yt, yp, labels))]
    pc = per_class(yt, yp, labels)
    for lab in labels:
        rows.append(prop_row(f"recall[{lab}]", "recall", pc[lab]["tp"], pc[lab]["tp"] + pc[lab]["fn"]))
    mm = [(r.get("mismatch_gold"), r.get("mismatch_pred")) for r in records if r.get("mismatch_gold") is not None]
    if mm:
        rows.append(prop_row("mismatch_type accuracy", "accuracy", sum(1 for g, p in mm if g == p), len(mm)))
    return rows


def score_alignment(records: list) -> list:
    """[8] M-recall · M-precision · M-F1 + NEI(LLM 실패)율.
    record: gold_M(bool), pred_M(bool), [nei(bool)]."""
    tp = sum(1 for r in records if r.get("gold_M") and r.get("pred_M"))
    fp = sum(1 for r in records if (not r.get("gold_M")) and r.get("pred_M"))
    fn = sum(1 for r in records if r.get("gold_M") and not r.get("pred_M"))
    _, _, f = prf1(tp, fp, fn)
    rows = [prop_row("M-recall", "recall", tp, tp + fn),
            prop_row("M-precision", "precision", tp, tp + fp),
            value_row("M-F1", "f1", f)]
    nei = [r for r in records if "nei" in r]
    if nei:
        rows.append(prop_row("NEI(LLM 실패)율", "nei-rate", sum(1 for r in nei if r["nei"]), len(nei)))
    return rows


def score_decide_verdict(records: list) -> list:
    """[9] exact-match (결정적 집계, 오차 0 기대). record: match(bool)."""
    return [prop_row("exact-match", "exact", sum(1 for r in records if r.get("match")), len(records))]


def score_explanation(records: list) -> list:
    """[10] 템플릿 accuracy(snapshot). record: template_match(bool). (opinion 품질은 별도 루브릭)."""
    return [prop_row("템플릿 accuracy(snapshot)", "accuracy", sum(1 for r in records if r.get("template_match")), len(records))]


STAGE_SCORERS = {
    2: score_extract, 3: score_normalize, 4: score_retrieve, 5: score_fetch, 6: score_rank,
    7: score_verdict_metric, 8: score_alignment, 9: score_decide_verdict, 10: score_explanation,
}
