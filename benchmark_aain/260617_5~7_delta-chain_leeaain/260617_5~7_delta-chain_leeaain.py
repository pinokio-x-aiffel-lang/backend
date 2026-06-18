"""증감(CHANGE_RATE) 체인 배선 전/후 delta 값 recall 벤치마크. [stage 5 + 7]

목적
    증감형 claim 은 단일 셀조회로는 절대조회 값(레벨)만 얻어 gold(전년대비 증감)와
    어긋난다(베이스라인 delta 적중 1/105). 본 PR 은 [5] fetch_kosis_data 가 같은 셀
    좌표를 기준 시점(compare_period)으로 한 번 더 조회하고 [7] compute_change 가
    (현재−기준) 증감을 계산하도록 배선했다. 그 배선 전/후 값 재현율을 통제 비교한다.

설계 (한 번 조회로 before/after 동시 산출)
    claim_type=CHANGE_RATE + compare_period 로 stage 5 를 1회 실행하면 evidence 에
    현재값(value)·기준값(compare_value)이 모두 담긴다. 동일 표 해소에서
      - before(배선 전)  = 단일 셀값(evidence.value) vs gold        → 레벨이라 거의 miss
      - after (배선 후)  = (value − compare_value) 증감 vs gold      → 정답 재현
    를 같이 채점한다(표 해소가 동일해 apples-to-apples; KOSIS 호출도 절반).

채점 대상 = T-figure delta 행 + 구체 시점(YYYY / YYYY-MM)
    gold.value 가 독립 정답(전년대비 증감 figure)인 행만. period 가 현재/불명인 행은
    기준 시점 산출 불가라 제외. 비교 기준 = 전년동월/전년(period − 1년, 같은 달).

값 일치: 단위(만/천/억) 보정 후 상대오차 ≤2% (baseline value_matches 와 동일).
    추가로 부호까지 맞는 signed-hit 를 더 엄격한 보조지표로 함께 보고.

실행: uv run x python benchmark/260617_5~7_delta-chain_leeaain/260617_5~7_delta-chain_leeaain.py [--limit N] [--concurrency K]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
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
HINT_SRC = ROOT / "benchmark_aain/data/260614_source_from_origin_for_retrieve_kosis_candidates.jsonl"
HERE = Path(__file__).resolve().parent
OUTJSON = HERE / "260617_5~7_delta-chain_leeaain_result.json"
OUTMD = HERE / "260617_5~7_delta-chain_leeaain_report.md"

# baseline 과 동일한 단위 스케일·delta 키워드(자기완결 위해 복사).
_SCALES = [1, 10, 100, 1e3, 1e4, 1e6, 1e8, 0.1, 0.01, 1e-3, 1e-4]
_DELTA_KW = ("증감", "증가", "감소", "전년", "전월", "대비")
_CONCRETE = re.compile(r"^\d{4}(-\d{2})?$")


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


def value_matches(gold, got, tol=0.02) -> bool:
    """단위(만/천/억) 무시하고 크기가 같은지(부호 무시 — baseline 동일)."""
    a, b = _to_float(gold), _to_float(got)
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


def signed_matches(gold, got) -> bool:
    """value_matches + 부호 일치(증가/감소 방향까지 맞아야)."""
    a, b = _to_float(gold), _to_float(got)
    if a is None or b is None or not value_matches(gold, got):
        return False
    return (a >= 0) == (b >= 0)


def is_delta(item_hint, gold_value) -> bool:
    if any(k in (item_hint or "") for k in _DELTA_KW):
        return True
    v = _to_float(gold_value)
    return v is not None and v < 0


def compare_period(period_value: str, period_type: str) -> str | None:
    """전년동월/전년 기준 시점 = period − 1년(같은 달). YYYY-MM·YYYY 만 처리."""
    s = (period_value or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})$", s)
    if m:
        return f"{int(m.group(1)) - 1}-{m.group(2)}"
    m = re.match(r"^(\d{4})$", s)
    if m:
        return str(int(m.group(1)) - 1)
    return None


def _slot(raw: str = "", llm: str = "") -> ValueSlot:
    return ValueSlot(raw=raw, llm_value=llm, is_inferred=False)


def build_master(row: dict) -> MasterSchema:
    """평가셋 행 → CHANGE_RATE claim(+compare_period) + 캡처 후보 주입. stage 5 만 돌릴 입력."""
    c = row["claim"]
    cid = row["claim_id"]
    pv = c.get("period_value_llm") or ""
    pt = c.get("period_type") or "Y"
    cp = compare_period(pv, pt)
    claim = Claim(
        claim_id=cid,
        article_id=f"row-{row['row_id']}",
        sentence="",
        claim_type=ClaimType.CHANGE_RATE,          # 증감 체인 활성화 → [5]가 2시점 조회
        subject=c.get("subject") or "",
        value=_slot(),                              # 조회에 미사용(채점은 evidence 값 기준)
        unit=c.get("unit") or "",
        aggregation="",
        period_type=pt,
        period_value=_slot(llm=pv),
        compare_period_value=_slot(raw="전년", llm=cp or ""),
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
    """stage 5(증감 2시점) 실행 → before(단일값)·after(증감차) 동시 채점."""
    gold = row.get("gold") or {}
    gv = gold.get("value")
    ms = build_master(row)
    cp = compare_period((row["claim"] or {}).get("period_value_llm") or "",
                        (row["claim"] or {}).get("period_type") or "Y")

    t0 = time.perf_counter()
    err = None
    try:
        await fetch_kosis_data(ms)
    except Exception as exc:  # noqa: BLE001 — 측정은 한 행 실패에 멈추지 않음
        err = f"{type(exc).__name__}: {exc}"
    dur = round(time.perf_counter() - t0, 2)

    evs = []
    for e in (ms.analysis[0].evidences or []):
        delta = (e.value - e.compare_value) if (e.value is not None and e.compare_value is not None) else None
        evs.append({
            "tbl_id": e.kosis_tbl_id, "item_id": e.kosis_item_id,
            "value": e.value, "compare_value": e.compare_value, "delta": delta,
            "unit": e.unit, "period": e.period, "compare_period": e.compare_period,
        })

    # before: 단일 셀값(레벨) vs gold(증감) — 현 동작
    before_hit = any(value_matches(gv, e["value"]) for e in evs)
    # after: 증감차(value − compare_value) vs gold — 배선 후
    delta_hit = any(e["delta"] is not None and value_matches(gv, e["delta"]) for e in evs)
    after_hit = before_hit or delta_hit
    # 보조: 부호까지 맞는 증감차
    delta_signed_hit = any(e["delta"] is not None and signed_matches(gv, e["delta"]) for e in evs)
    n_with_compare = sum(1 for e in evs if e["compare_value"] is not None)

    return {
        "row_id": row["row_id"], "claim_id": row["claim_id"],
        "subject": (row["claim"] or {}).get("subject"),
        "population": (row["claim"] or {}).get("population"),
        "period": (row["claim"] or {}).get("period_value_llm"),
        "compare_period_derived": cp,
        "gold_value": gv, "gold_unit": gold.get("unit"),
        "item_hint": row.get("_item_hint"),
        "n_candidates": len(row.get("candidates", [])),
        "n_evidences": len(evs), "n_evidences_with_compare": n_with_compare,
        "evidences": evs,
        "before_hit": before_hit, "delta_hit": delta_hit, "after_hit": after_hit,
        "delta_signed_hit": delta_signed_hit,
        "new_by_delta": after_hit and not before_hit,
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
            tag = "DELTA" if r["delta_hit"] else ("base " if r["before_hit"] else ("ERR" if r["error"] else "miss"))
            print(f"[{done[0]:>3}/{total}] {tag} ev={r['n_evidences']:>2} cmp={r['n_evidences_with_compare']:>2} "
                  f"{str(r['subject'])[:20]:20} gold={r['gold_value']}")
            return r

    out = await asyncio.gather(*(guarded(x) for x in rows))
    return sorted(out, key=lambda r: r["row_id"])


def summarize(items: list[dict]) -> dict:
    n = len(items)
    before = sum(1 for r in items if r["before_hit"])
    after = sum(1 for r in items if r["after_hit"])
    delta = sum(1 for r in items if r["delta_hit"])
    delta_signed = sum(1 for r in items if r["delta_signed_hit"])
    new_by_delta = sum(1 for r in items if r["new_by_delta"])
    with_compare = sum(1 for r in items if r["n_evidences_with_compare"] > 0)
    errs = sum(1 for r in items if r["error"])
    return {
        "scored_rows": n,
        "rows_with_compare_evidence": with_compare,
        "errors": errs,
        "before_recall": round(before / n, 4) if n else 0.0,
        "after_recall": round(after / n, 4) if n else 0.0,
        "before_hits": before, "after_hits": after,
        "delta_path_hits": delta, "delta_signed_hits": delta_signed,
        "new_rows_recovered_by_delta_chain": new_by_delta,
    }


def render_md(s: dict) -> str:
    n = s["scored_rows"]
    L = ["# 260617_5~7_delta-chain_leeaain — 증감 체인 배선 전/후 값 recall", ""]
    L += ["## 1. 개요",
          "증감형(CHANGE_RATE) claim 은 단일 셀조회로는 레벨값만 얻어 gold(전년대비 증감)와 "
          "어긋난다(베이스라인 1/105). 본 PR 은 [5] fetch_kosis_data 가 같은 좌표를 기준 시점으로 "
          "한 번 더 조회하고 [7] compute_change 가 (현재−기준) 증감을 계산하도록 배선했다. "
          "동일 표 해소에서 단일값(before) vs 증감차(after) 를 함께 채점한다.", ""]
    L += ["## 2. 무엇을 테스트했나",
          f"- 채점 대상: T-figure delta 행 + 구체 시점(YYYY/YYYY-MM) **{n}건** "
          "(period 현재/불명 제외, 전부 전년동월/전년 계열).",
          "- 비교 기준 = period − 1년(같은 달). 값 일치 = 단위보정 후 상대오차 ≤2%.",
          f"- 기준 시점 evidence 확보 행: {s['rows_with_compare_evidence']}/{n}, 에러 {s['errors']}.", ""]
    L += ["## 3. 결과 — 배선 전/후", "",
          "| 지표 | 배선 전(before) | 배선 후(after) |",
          "|---|---|---|",
          f"| delta 값 recall | **{s['before_recall']:.3f}** ({s['before_hits']}/{n}) | "
          f"**{s['after_recall']:.3f}** ({s['after_hits']}/{n}) |", "",
          f"- 증감차 경로 적중(value−compare): **{s['delta_path_hits']}/{n}**  "
          f"(그중 부호까지 일치: {s['delta_signed_hits']}/{n})",
          f"- 증감 체인으로 **새로 회수된 행: {s['new_rows_recovered_by_delta_chain']}/{n}** "
          "(before miss → after hit)", ""]
    L += ["## 4. 한계 / 범위",
          "- claim.value(주장 수치)가 평가셋에 없어 **값 재현율**만 측정(stage 7 T/F 판정 별도).",
          "- value_matches 는 부호 무시(크기) — baseline 과 동일 기준. signed-hit 를 보조로 병기.",
          "- 후보 top-N 고정(stage 4 재검색 생략). 정답 표가 후보에 없던 행은 구조적 miss.",
          "- 직접 증감-item 매칭 행은 단일값이 이미 gold → before/after 모두 hit(증감차 무관)."]
    return "\n".join(L)


def _load_item_hints() -> dict[tuple, str]:
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
    rows = [r for r in rows
            if (r.get("gold") or {}).get("value") is not None
            and (r.get("gold") or {}).get("value_source") == "figure"]
    hints = _load_item_hints()
    out = []
    for r in rows:
        h = hints.get((r["row_id"], r["claim_id"]))
        r["_item_hint"] = h
        if not is_delta(h, (r.get("gold") or {}).get("value")):
            continue
        pv = str((r.get("claim") or {}).get("period_value_llm") or "")
        if not _CONCRETE.match(pv):       # 기준 시점 산출 불가 → 제외
            continue
        out.append(r)
    return out[:limit] if limit else out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=5)
    args = ap.parse_args()

    rows = load_rows(args.limit)
    print(f"증감 체인 stage 5 실행 + before/after delta 채점 — {len(rows)}건, 동시 {args.concurrency}\n")
    items = asyncio.run(run_all(rows, args.concurrency))
    summary = summarize(items)

    OUTJSON.write_text(json.dumps(
        {"source": str(SRC), "mode": "stage5(change_rate 2-period, candidates injected)",
         "scored": "T-figure delta rows with concrete period",
         "summary": summary, "records": items},
        ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    OUTMD.write_text(render_md(summary), encoding="utf-8")

    print(f"\n{json.dumps(summary, ensure_ascii=False)}")
    print(f"저장:\n  {OUTJSON}\n  {OUTMD}")


if __name__ == "__main__":
    main()
