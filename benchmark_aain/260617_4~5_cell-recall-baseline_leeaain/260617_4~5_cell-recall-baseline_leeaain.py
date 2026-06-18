"""[5] fetch_kosis_data 셀-조회 값 recall 베이스라인 (stage 4 후보 고정).

목적
    1단계 itmId LLM 폴백 도입 '전' 기준선을 고정한다. 캡처된 후보 top-N 을
    그대로 주입(stage 4 재검색 생략)하고 **stage 5(fetch_kosis_data)만 재실행**해,
    stage 5 의 셀 좌표 해소(itmId/objL)만 분리 측정한다. stage 4 검색 drift 가
    섞이지 않아 itmId 수정 전후 비교가 apples-to-apples.

채점 대상 = T 행만 (gold.value_source == "figure")
    gold.value 출처가 T=기사 figure(독립 정답)인 반면 F/M=live_capture(우리가
    캡처한 값 자체 = 순환참조)라, 진짜 recall 은 T 행으로만 잰다. F/M 독립 정답값은
    병인님 xlsx(`원래 통계표 수치`)에 있어 Task#2 에서 백필 예정.

부산물
    값이 적중한 행의 (tbl_id, itm_id) 는 사실상 정답 표/항목 → gold_tbl_id 자동시드로
    result.json 에 함께 적재(Task#2 부트스트랩 입력).

실행:  uv run x python benchmark/260617_4~5_cell-recall-baseline_leeaain/260617_4~5_cell-recall-baseline_leeaain.py [--limit N] [--concurrency K]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from collections import Counter
from pathlib import Path

from src.modules.fetch_kosis_data import fetch_kosis_data
from src.schemas.runtime import (
    Claim,
    ClaimAnalysis,
    ClaimType,
    KosisCandidate,
    KosisQuery,
    KosisSearch,
    MasterSchema,
    ValueSlot,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "benchmark_aain/data/260614_source_from_origin_for_fetch_kosis_data.jsonl"
# gold_item_hint(항목명) 조인용 — delta(증감형) gold 분류에 사용.
HINT_SRC = ROOT / "benchmark_aain/data/260614_source_from_origin_for_retrieve_kosis_candidates.jsonl"
HERE = Path(__file__).resolve().parent
OUTJSON = HERE / "260617_4~5_cell-recall-baseline_leeaain_result.json"
OUTMD = HERE / "260617_4~5_cell-recall-baseline_leeaain_report.md"

# 단위 환산 스케일(만/억/천 등). build_eval_sets_from_capture.value_matches 와 동일 로직 —
# 단위표기(천명/명/만명)가 달라도 같은 값이면 매칭. 자기완결 위해 복사(출처 명시).
_SCALES = [1, 10, 100, 1e3, 1e4, 1e6, 1e8, 0.1, 0.01, 1e-3, 1e-4]

# 증감형 gold 키워드(항목명 기준). 절대값 셀조회로는 재현 불가 → 별도 집계(주지표 제외).
# run_2to5_gold_eval._DELTA_KW 와 동일 기준.
_DELTA_KW = ("증감", "증가", "감소", "전년", "전월", "대비")


def is_delta(item_hint: str | None, gold_value) -> bool:
    """항목명에 증감 키워드가 있거나 gold 값이 음수면 증감형으로 간주."""
    if any(k in (item_hint or "") for k in _DELTA_KW):
        return True
    v = _to_float(gold_value)
    return v is not None and v < 0


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


def value_matches(a, b, tol=0.02) -> bool:
    """단위(만/천/억) 무시하고 같은 값인지. a=gold, b=evidence 값."""
    a, b = _to_float(a), _to_float(b)
    if a is None or b is None:
        return False
    for s in _SCALES:
        base = b * s
        if abs(base) < 1e-9:
            if abs(a) < 1e-9:
                return True
            continue
        if abs(abs(a) - abs(base)) / abs(base) <= tol:
            return True
    return False


def canon_period(p) -> str | None:
    """YYYY-MM / YYYY / YYYY-Qn / KOSIS PRD_DE → 비교용 정규형. 범위는 None."""
    p = str(p or "").strip()
    if not p or "~" in p:
        return None
    m = re.match(r"^(\d{4})-Q([1-4])$", p)
    if m:
        return f"{m.group(1)}{int(m.group(2)):02d}"
    m = re.match(r"^(\d{4})-(\d{2})$", p)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    if re.match(r"^\d{4}$", p):
        return p
    d = re.sub(r"\D", "", p)
    return d or None


def _slot(raw: str = "", llm: str = "") -> ValueSlot:
    return ValueSlot(raw=raw, llm_value=llm, is_inferred=False)


def build_master(row: dict) -> MasterSchema:
    """평가셋 행 → 단일 claim + 캡처 후보 주입 MasterSchema. stage 5 만 돌릴 입력."""
    c = row["claim"]
    cid = row["claim_id"]
    claim = Claim(
        claim_id=cid,
        article_id=f"row-{row['row_id']}",
        sentence="",
        claim_type=ClaimType.ABSOLUTE,  # stage 4-5 는 claim_type 미분기
        subject=c.get("subject") or "",
        value=_slot(),  # 조회에 미사용
        unit=c.get("unit") or "",
        aggregation="",
        period_type=c.get("period_type") or "Y",
        period_value=_slot(llm=c.get("period_value_llm") or ""),
        population=c.get("population") or "",
        cited_source="",
    )
    candidates = [
        KosisCandidate(org_id=h.get("org_id") or "", tbl_id=h.get("tbl_id") or "",
                       tbl_nm=h.get("tbl_nm") or "")
        for h in row.get("candidates", [])
    ]
    analysis = ClaimAnalysis(
        claim_id=cid,
        kosis_search=KosisSearch(api="", query="", params="", hits=len(candidates),
                                 success=1, duration_ms=0),
        candidates=candidates,
        kosis_query=KosisQuery(api="", tbl_id="", params="", rows_returned=0,
                               success=0, duration_ms=0),
    )
    ms = MasterSchema(content="")
    ms.claims = [claim]
    ms.analysis = [analysis]
    return ms


async def score_row(row: dict) -> dict:
    """stage 5 재실행 → evidences 를 gold.value 와 대조."""
    gold = row.get("gold") or {}
    gv = gold.get("value")
    claim_period = (row["claim"] or {}).get("period_value_llm")
    ms = build_master(row)

    t0 = time.perf_counter()
    err = None
    try:
        await fetch_kosis_data(ms)
    except Exception as exc:  # noqa: BLE001 — 베이스라인 측정은 한 행 실패에 멈추지 않음
        err = f"{type(exc).__name__}: {exc}"
    dur = round(time.perf_counter() - t0, 2)

    an = ms.analysis[0]
    evs = [
        {"tbl_id": e.kosis_tbl_id, "item_id": e.kosis_item_id, "value": e.value,
         "unit": e.unit, "period": e.period, "population_fallback": e.population_fallback,
         "match_source": e.match_source}
        for e in (an.evidences or [])
    ]
    # 값 적중: 어느 evidence 든 gold.value 와 (단위보정) 일치
    hit_ev = next((e for e in evs if value_matches(gv, e["value"])), None)
    value_hit = hit_ev is not None
    # 값+시점 적중: 적중 evidence 의 시점이 claim 시점과 같은가
    vp_hit = bool(hit_ev) and canon_period(hit_ev["period"]) == canon_period(claim_period)

    return {
        "row_id": row["row_id"], "label": row["label"], "claim_id": row["claim_id"],
        "subject": (row["claim"] or {}).get("subject"),
        "population": (row["claim"] or {}).get("population"),
        "gold_value": gv, "gold_unit": gold.get("unit"),
        "gold_item_hint": row.get("_item_hint"), "is_delta": row.get("_is_delta", False),
        "old_consistency_flag": gold.get("consistency_flag"),
        "n_candidates": len(row.get("candidates", [])),
        "n_evidences": len(evs), "evidences": evs,
        "value_hit": value_hit, "value_period_hit": vp_hit,
        # gold_tbl_id 자동시드: 값 적중 시 그 tbl_id/itm_id 가 정답 후보
        "seed_gold_tbl_id": hit_ev["tbl_id"] if hit_ev else None,
        "seed_gold_item_id": hit_ev["item_id"] if hit_ev else None,
        "duration_s": dur, "error": err,
    }


async def run_all(rows: list[dict], conc: int) -> list[dict]:
    sem = asyncio.Semaphore(conc)
    total = len(rows)
    done = [0]

    async def guarded(row):
        async with sem:
            r = await score_row(row)
            done[0] += 1
            tag = "HIT " if r["value_hit"] else ("ERR" if r["error"] else "miss")
            print(f"[{done[0]:>3}/{total}] {tag} ev={r['n_evidences']:>2} "
                  f"{str(r['subject'])[:24]:24} gold={r['gold_value']}")
            return r

    out = await asyncio.gather(*(guarded(x) for x in rows))
    return sorted(out, key=lambda r: r["row_id"])


def summarize(items: list[dict]) -> dict:
    n = len(items)
    absol = [r for r in items if not r["is_delta"]]      # 절대값형 — stage 5 재현 가능
    delta = [r for r in items if r["is_delta"]]          # 증감형 — 절대조회로 재현 불가
    a_vh = sum(1 for r in absol if r["value_hit"])
    a_vph = sum(1 for r in absol if r["value_period_hit"])
    with_ev = sum(1 for r in items if r["n_evidences"] > 0)
    errs = sum(1 for r in items if r["error"])
    seeds = sum(1 for r in absol if r["seed_gold_tbl_id"])
    old = dict(Counter(r["old_consistency_flag"] for r in items))
    return {
        "scored_rows": n,
        "absolute_rows": len(absol), "delta_rows_excluded": len(delta),
        "rows_with_evidence": with_ev,
        "errors": errs,
        # 주지표: 절대값형 gold 에 대한 stage 5 재현율(후보 고정)
        "value_recall_absolute": round(a_vh / len(absol), 4) if absol else 0.0,
        "value_period_recall_absolute": round(a_vph / len(absol), 4) if absol else 0.0,
        "value_hits_absolute": a_vh, "value_period_hits_absolute": a_vph,
        # 참고: 증감형은 절대조회로 재현 불가(거의 0이 정상)
        "delta_value_hits": sum(1 for r in delta if r["value_hit"]),
        "auto_seed_gold_tbl_id": seeds,
        "prev_capture_consistency_flag": old,
    }


def render_md(s: dict, src_label: str) -> str:
    L = ["# 260617_4~5_cell-recall-baseline_leeaain", ""]
    L += ["## 1. 개요",
          "1단계(itmId LLM 폴백) 도입 **전** 기준선. 캡처된 stage 4 후보 top-N 을 고정 주입하고 "
          "**stage 5(fetch_kosis_data)만 재실행**해, 셀 좌표 해소(itmId/objL)가 KOSIS 공식값을 "
          "재현하는 비율을 잰다. stage 4 검색 drift 를 배제해 itmId 수정 전후 비교를 깨끗하게 한다.", ""]
    L += ["## 2. 무엇을 테스트했나",
          f"- 소스: `{src_label}`",
          "- 채점 대상: **T 행 (gold.value_source == \"figure\")** — 독립 정답값.",
          "  F/M 의 gold.value 는 live_capture(순환참조)라 제외; 독립 정답값은 병인님 xlsx 에서 백필 예정(Task#2).",
          "- 값 일치: 단위(만/천/억) 보정 후 상대오차 ≤2%. 시점은 KOSIS PRD_DE 정규화 비교.", ""]
    L += ["## 3. 지표 결과",
          f"- 채점 행: {s['scored_rows']} = 절대값형 {s['absolute_rows']} + 증감형(제외) {s['delta_rows_excluded']}",
          f"  (evidence 확보 {s['rows_with_evidence']}, 에러 {s['errors']})",
          f"- **절대값 recall: {s['value_recall_absolute']:.3f}** "
          f"({s['value_hits_absolute']}/{s['absolute_rows']})  ← 주지표",
          f"- 절대값+시점 recall: {s['value_period_recall_absolute']:.3f} "
          f"({s['value_period_hits_absolute']}/{s['absolute_rows']})",
          f"- (참고) 증감형 적중: {s['delta_value_hits']}/{s['delta_rows_excluded']} "
          "— 절대조회로 재현 불가(거의 0이 정상)",
          f"- gold_tbl_id 자동시드(값 적중행): {s['auto_seed_gold_tbl_id']} 건 → Task#2 입력",
          f"- (참고) 캡처 당시 consistency_flag 분포: {s['prev_capture_consistency_flag']}", ""]
    L += ["## 4. 한계 / 범위",
          "- 후보 top-N 고정(stage 4 재검색 생략) → 정답 표가 후보에 없던 행은 구조적으로 miss. "
          "stage 4 표 recall 분리는 gold_tbl_id 완성(Task#2) 후 별도 측정.",
          "- 값 적중이 '우연히 다른 표에서 같은 값'일 수 있음(드묾) → gold_tbl_id 검수로 보강.",
          "- T 행만 독립 채점. F/M/NEI 는 본 베이스라인 범위 밖."]
    return "\n".join(L)


def _load_item_hints() -> dict[tuple, str]:
    """(row_id, claim_id) → gold_item_hint. stage4 파일에서 조인(delta 분류용)."""
    out: dict[tuple, str] = {}
    for ln in HINT_SRC.read_text(encoding="utf-8").splitlines():
        if not (s := ln.strip()):
            continue
        r = json.loads(s)
        if r.get("gold_item_hint"):
            out[(r["row_id"], r["claim_id"])] = r["gold_item_hint"]
    return out


def load_rows(limit: int) -> list[dict]:
    rows = [json.loads(s) for ln in SRC.read_text(encoding="utf-8").splitlines()
            if (s := ln.strip())]
    # 독립 정답값(T figure)만 채점
    rows = [r for r in rows
            if (r.get("gold") or {}).get("value") is not None
            and (r.get("gold") or {}).get("value_source") == "figure"]
    hints = _load_item_hints()
    for r in rows:
        r["_item_hint"] = hints.get((r["row_id"], r["claim_id"]))
        r["_is_delta"] = is_delta(r["_item_hint"], (r.get("gold") or {}).get("value"))
    return rows[:limit] if limit else rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=5)
    args = ap.parse_args()

    rows = load_rows(args.limit)
    print(f"stage 5 재실행 + gold(T figure) 값 채점 — {len(rows)}건, 동시 {args.concurrency}\n")
    items = asyncio.run(run_all(rows, args.concurrency))
    summary = summarize(items)

    OUTJSON.write_text(json.dumps(
        {"source": str(SRC), "mode": "stage5-only(candidates injected)",
         "scored": "T rows, value_source=figure",
         "summary": summary, "records": items},
        ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    OUTMD.write_text(render_md(summary, SRC.name), encoding="utf-8")

    print(f"\n{json.dumps(summary, ensure_ascii=False)}")
    print(f"저장:\n  {OUTJSON}\n  {OUTMD}")


if __name__ == "__main__":
    main()
