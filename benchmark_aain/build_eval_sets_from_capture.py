"""라이브 캡처(260614_capture_master_stage1to8.json) → 4·5·6·7·8·10단계 평가셋 슬라이스.

캡처 = 실제 파이프라인 1회 산출(실제 KOSIS/LLM). 각 단계 '입력'을 잘라내고 gold 는
마스터 라벨/공식값(옵션 ②)로 붙인다. 값은 캡처/마스터에서만 옴(무생성).

[수정 A] 한 문장→다중 claim 오배정 방지:
  - True행 공식값(gold_figures)을 claim 의 정규화 값과 단위보정 매칭해 '그 claim'에만 부여.
  - 매칭 실패/무증거/값불일치 행은 gold=null + scorable=false(채점 제외)로 명시.
  - 7단계에 claim.period_llm·evidence.period 추가(mismatch PERIOD 채점용).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "benchmark_aain/data"
CAPTURE = DATA / "260614_capture_master_stage1to8.json"
PFX = "260614_source_from_origin_for_"

STAGE7_GOLD = {"T": "T", "M": "T", "F": "F", "NEI": "N"}  # 7단계 기준(M=값일치→T, 8단계서 M)
# 단위 환산 스케일(만/억/천 등). 단위표기가 달라도 같은 값이면 매칭.
_SCALES = [1, 10, 100, 1e3, 1e4, 1e6, 1e8, 0.1, 0.01, 1e-3, 1e-4]


def _write_jsonl(name, rows):
    (DATA / name).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"  wrote {len(rows):4d} rows -> {name}")


def _to_float(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    m = re.search(r"[-+]?\d[\d,]*\.?\d*", str(s))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _figvals(v):
    return v if isinstance(v, list) else [v]


def value_matches(a, b, tol=0.02):
    """단위(만/천/억 등) 무시하고 같은 값인지. a=claim 정규화값, b=figure/evidence 값."""
    if a is None or b is None:
        return False
    for bv in _figvals(b):
        bf = _to_float(bv)
        if bf is None:
            continue
        for s in _SCALES:
            base = bf * s
            if abs(base) < 1e-9:
                if abs(a) < 1e-9:
                    return True
                continue
            if abs(abs(a) - abs(base)) / abs(base) <= tol:
                return True
    return False


def match_figure(claim_val, gold_figures):
    """claim 값과 단위보정 매칭되는 gold figure 1개. (matched_value, figure, ok)."""
    for f in gold_figures or []:
        for bv in _figvals(f.get("value")):
            if value_matches(claim_val, bv):
                return _to_float(bv), f, True
    return None, None, False


def consistency(label, claim_val, ev_val):
    """옵션② 정합성: T·M=값일치, F=값불일치 여야 정합. 단위보정 비교."""
    if label == "NEI":
        return "n/a"
    cv, ev = _to_float(claim_val), _to_float(ev_val)
    if ev is None:
        return "no_evidence"
    if cv is None:
        return "claim_unparsed"
    close = value_matches(cv, ev)
    if label in ("T", "M"):
        return "ok" if close else "mismatch"
    return "ok" if not close else "mismatch"  # F


def main():
    cap = json.load(open(CAPTURE, encoding="utf-8"))
    s4, s5, s6, s7, s8, s10 = [], [], [], [], [], []

    for entry in cap:
        row_id, label = entry["row_id"], entry["label"]
        gold_figs = entry.get("gold_figures")
        res = entry.get("result") or {}
        claims = {c["claim_id"]: c for c in res.get("claims", [])}
        analyses = {a["claim_id"]: a for a in res.get("analysis", [])}

        for cid, c in claims.items():
            a = analyses.get(cid, {})
            cands = a.get("candidates", [])
            evs = a.get("evidences", [])
            cell_attempts = {ca["tbl_id"]: ca for ca in a.get("cell_attempts", [])}
            ks = a.get("kosis_search", {})
            value_llm = (c.get("value") or {}).get("llm_value")
            period_llm = (c.get("period_value") or {}).get("llm_value")
            claim_val = _to_float(value_llm)
            ev0 = evs[0] if evs else None
            ev0_val = ev0.get("value") if ev0 else None

            # claim↔figure 매칭(True행만). 매칭된 figure 값이 그 claim 의 공식 gold.
            fig_val, fig, fig_ok = match_figure(claim_val, gold_figs) if label == "T" else (None, None, False)
            cons = consistency(label, value_llm, ev0_val)

            # ---- [4] retrieve_kosis_candidates (gold_tbl_id 주석 필요 → scorable=false) ----
            s4.append({
                "row_id": row_id, "label": label, "claim_id": cid,
                "subject": c.get("subject"), "unit": c.get("unit"),
                "period_type": c.get("period_type"), "population": c.get("population"),
                "claim_value_raw": (c.get("value") or {}).get("raw"),
                "candidates": [{"rank": i + 1, "org_id": h.get("org_id"), "tbl_id": h.get("tbl_id"),
                                "tbl_nm": h.get("tbl_nm"), "stat_nm": h.get("stat_nm")}
                               for i, h in enumerate(cands)],
                "search_success": ks.get("success"), "search_hits": ks.get("hits"),
                "gold_tbl_id": None, "gold_item_hint": (fig.get("item") if fig else None),
                "scorable": False, "scorable_reason": "gold_tbl_id 주석 필요(gap C)",
            })

            # ---- [5] fetch_kosis_data ----
            if label == "T":
                gv, vsrc = fig_val, "figure"
                s5_score = fig_ok
                s5_reason = "ok" if fig_ok else "claim↔figure 값 매칭 실패"
            elif label == "NEI":
                gv, vsrc = None, "none"
                s5_score, s5_reason = False, "검증대상 아님(공식값 없음이 정답)"
            else:  # F, M
                gv, vsrc = ev0_val, "live_capture"
                s5_score = (ev0 is not None and cons == "ok")
                s5_reason = "ok" if s5_score else f"무증거/정합실패({cons})"
            s5.append({
                "row_id": row_id, "label": label, "claim_id": cid,
                "claim": {"subject": c.get("subject"), "population": c.get("population"),
                          "period_type": c.get("period_type"), "period_value_llm": period_llm, "unit": c.get("unit")},
                "candidates": [{"org_id": h.get("org_id"), "tbl_id": h.get("tbl_id"), "tbl_nm": h.get("tbl_nm")} for h in cands],
                "captured_evidences": [{"tbl_id": e.get("kosis_tbl_id"), "value": e.get("value"), "unit": e.get("unit"),
                                        "period": e.get("period"), "population_fallback": e.get("population_fallback"),
                                        "kosis_item_id": e.get("kosis_item_id")} for e in evs],
                "gold": {"value": gv, "unit": (ev0.get("unit") if ev0 else None), "value_source": vsrc,
                         "consistency_flag": cons},
                "scorable": s5_score, "scorable_reason": s5_reason,
            })

            # ---- [6] rank_evidence (후보 표 >=2 만) ----
            if len(evs) >= 2:
                best = None
                if label == "T" and fig_ok:
                    for i, e in enumerate(evs):
                        if value_matches(_to_float(e.get("value")), fig_val):
                            best = i
                            break
                s6.append({
                    "row_id": row_id, "label": label, "claim_id": cid,
                    "claim": {"subject": c.get("subject"), "population": c.get("population"),
                              "unit": c.get("unit"), "period": f"{c.get('period_type')}:{period_llm}"},
                    "evidences": [{"tbl_id": e.get("kosis_tbl_id"), "table_name": e.get("table_name"), "value": e.get("value"),
                                   "axes": list((cell_attempts.get(e.get("kosis_tbl_id"), {}).get("axes") or {}).keys())} for e in evs],
                    "gold_best_index": best,
                    "scorable": best is not None,
                    "scorable_reason": "ok" if best is not None else "gold_best_index 주석 필요(gap C/D)",
                })

            # ---- [7] calculate_metric (period 필드 추가) ----
            if label == "NEI":
                s7_score, s7_reason = True, "ok(gold=N)"
            else:
                s7_score = (ev0 is not None and cons == "ok")
                s7_reason = "ok" if s7_score else f"무증거/정합실패({cons}) → 검색오류를 모듈오류로 오채점 방지"
            s7.append({
                "row_id": row_id, "label": label, "claim_id": cid,
                "gold_verdict_stage7": STAGE7_GOLD.get(label),
                "has_evidence": ev0 is not None,
                "claim": {"value_llm": value_llm, "claim_type": c.get("claim_type"),
                          "unit": c.get("unit"), "period_llm": period_llm},
                "evidence": ({"value": ev0_val, "unit": ev0.get("unit"), "period": ev0.get("period"),
                              "population_fallback": ev0.get("population_fallback")} if ev0 else None),
                "evidence_value_source": ("figure" if (label == "T" and fig_ok) else ("live_capture" if ev0 else "none")),
                "consistency_flag": cons,
                "scorable": s7_score, "scorable_reason": s7_reason,
            })

            # ---- [8] check_alignment (label in {T,M} + evidence + 값정합) ----
            if label in ("T", "M") and ev0 is not None:
                s8.append({
                    "row_id": row_id, "label": label, "claim_id": cid,
                    "claim": {"sentence": c.get("sentence"), "subject": c.get("subject"), "population": c.get("population"),
                              "unit": c.get("unit"), "aggregation": c.get("aggregation"), "period_llm": period_llm},
                    "evidence": {"table_name": ev0.get("table_name"), "subject": ev0.get("subject"), "population": ev0.get("population"),
                                 "unit": ev0.get("unit"), "period": ev0.get("period"), "population_fallback": ev0.get("population_fallback")},
                    "gold": {"aligned": (label == "T"), "dimension": None},
                    "scorable": (cons == "ok"),  # 값일치(=7단계 T 통과) 케이스만 정합성 판정 의미
                    "scorable_reason": "ok" if cons == "ok" else f"값정합 아님({cons}) → 8단계 대상 아님; dimension(M) 주석 필요",
                })

            # ---- [10] generate_explanation ----
            verdict10 = "N" if label == "NEI" else label
            if label == "T":
                kv = str(fig_val) if fig_ok else (str(ev0_val) if ev0_val is not None else None)
            elif label in ("F", "M"):
                kv = str(ev0_val) if ev0_val is not None else None
            else:
                kv = None
            # F/M 인데 공식값 없으면 템플릿이 깨짐 → scorable=false
            s10_score = not (label in ("F", "M") and kv is None)
            s10.append({
                "row_id": row_id, "label": label, "claim_id": cid,
                "claim": {"subject": c.get("subject"), "unit": c.get("unit"),
                          "period_type": c.get("period_type"), "period_llm": period_llm},
                "claim_result": {"verdict": verdict10, "claim_value": value_llm, "kosis_value": kv,
                                 "mismatch_type": None, "evidence": [{"table_name": ev0.get("table_name")}] if ev0 else []},
                "gold_template": None, "opinion_rubric": ["분포 반영", "verdict와 모순 없음", "환각 없음"],
                "scorable": s10_score,
                "scorable_reason": "ok" if s10_score else "verdict=F/M인데 공식값 없음 → 템플릿 비현실",
            })

    print("== 캡처 기반 단계 생성(수정 A) ==")
    for nm, rows in [("retrieve_kosis_candidates", s4), ("fetch_kosis_data", s5), ("rank_evidence", s6),
                     ("calculate_metric", s7), ("check_alignment", s8), ("generate_explanation", s10)]:
        _write_jsonl(f"{PFX}{nm}.jsonl", rows)

    def sc(rows):
        return f"{sum(1 for r in rows if r.get('scorable'))}/{len(rows)} scorable " + str(dict(Counter(r['label'] for r in rows if r.get('scorable'))))
    print("\n[scorable 요약]")
    print("  4 retrieve :", sc(s4))
    print("  5 fetch    :", sc(s5))
    print("  6 rank     :", sc(s6))
    print("  7 calc     :", sc(s7))
    print("  8 align    :", sc(s8))
    print("  10 explain :", sc(s10))


if __name__ == "__main__":
    main()
