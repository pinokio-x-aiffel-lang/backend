"""진단: 절대값 T 55건의 무증거 원인을 분류 → itmId LLM 폴백이 손댈 수 있는 상한 측정.

cell_attempts(후보 표별 시도)의 실패 사유를 본다:
  - 한 후보라도 itm_id 해소됨 → itmId 가 벽이 아님(실패는 축/시점/셀 = 폴백 무관)
  - 모든 후보가 itmId 매칭 실패 → 'pure itmId 벽' = 항목 LLM 폴백의 직접 타깃

실행:  uv run x python benchmark/260617_4~5_cell-recall-baseline_leeaain/diag_itmid_addressable.py
"""
from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from pathlib import Path

from src.modules.fetch_kosis_data import fetch_kosis_data
from src.schemas.runtime import (
    Claim, ClaimAnalysis, ClaimType, KosisCandidate, KosisQuery, KosisSearch,
    MasterSchema, ValueSlot,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "benchmark_aain/data/260614_source_from_origin_for_fetch_kosis_data.jsonl"
HINT = ROOT / "benchmark_aain/data/260614_source_from_origin_for_retrieve_kosis_candidates.jsonl"
_DELTA_KW = ("증감", "증가", "감소", "전년", "전월", "대비")


def _f(s):
    m = re.search(r"[-+]?\d[\d,]*\.?\d*", str(s or ""))
    return float(m.group(0).replace(",", "")) if m else None


def is_delta(hint, gv):
    if any(k in (hint or "") for k in _DELTA_KW):
        return True
    v = _f(gv)
    return v is not None and v < 0


def slot(llm=""):
    return ValueSlot(raw="", llm_value=llm, is_inferred=False)


def build(row):
    c = row["claim"]
    claim = Claim(claim_id=row["claim_id"], article_id=f"r{row['row_id']}", sentence="",
                  claim_type=ClaimType.ABSOLUTE, subject=c.get("subject") or "", value=slot(),
                  unit=c.get("unit") or "", aggregation="", period_type=c.get("period_type") or "Y",
                  period_value=slot(c.get("period_value_llm") or ""),
                  population=c.get("population") or "", cited_source="")
    cands = [KosisCandidate(org_id=h.get("org_id") or "", tbl_id=h.get("tbl_id") or "",
                            tbl_nm=h.get("tbl_nm") or "") for h in row.get("candidates", [])]
    an = ClaimAnalysis(claim_id=row["claim_id"],
                       kosis_search=KosisSearch(api="", query="", params="", hits=len(cands), success=1, duration_ms=0),
                       candidates=cands,
                       kosis_query=KosisQuery(api="", tbl_id="", params="", rows_returned=0, success=0, duration_ms=0))
    ms = MasterSchema(content="")
    ms.claims = [claim]
    ms.analysis = [an]
    return ms


def categorize(an) -> str:
    if an.evidences:
        return "has_evidence"
    atts = an.cell_attempts or []
    if not atts:
        return "no_candidates"
    any_item = any(a.itm_id is not None for a in atts)
    if any_item:
        # 항목 해소된 후보들의 에러로 세분 — 무엇이 진짜 첫 타깃인지.
        errs = [a.error or "" for a in atts if a.itm_id is not None]
        if any("셀 매칭 0건" in e for e in errs):
            return "item_ok__cell_empty(시점/분류 불일치)"   # 쿼리는 다 짰는데 데이터 0
        if any("분류축" in e and "매칭 실패" in e for e in errs):
            return "item_ok__axis_fail(모집단/지역)"        # 축 코드를 못 박음
        if any("셀 조회 실패" in e for e in errs):
            return "item_ok__fetch_err(rate limit?)"
        if any((">4" in e or "미지원" in e) for e in errs):
            return "item_ok__too_many_axes(>4)"
        return "item_ok__other"
    errs = [a.error or "" for a in atts]
    if all("메타 조회 실패" in e for e in errs):
        return "no_ev_meta_fail"
    return "no_ev_pure_itmid"                  # itmId 벽 = 항목 LLM 폴백 직접 타깃


async def main():
    rows = [json.loads(s) for ln in SRC.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]
    rows = [r for r in rows if (r.get("gold") or {}).get("value") is not None
            and (r.get("gold") or {}).get("value_source") == "figure"]
    hints = {}
    for ln in HINT.read_text(encoding="utf-8").splitlines():
        if (s := ln.strip()):
            d = json.loads(s)
            if d.get("gold_item_hint"):
                hints[(d["row_id"], d["claim_id"])] = d["gold_item_hint"]
    rows = [r for r in rows if not is_delta(hints.get((r["row_id"], r["claim_id"])), (r.get("gold") or {}).get("value"))]
    print(f"절대값 T 행: {len(rows)}")

    sem = asyncio.Semaphore(6)
    cats = Counter()
    detail = {}

    async def run(row):
        async with sem:
            ms = build(row)
            try:
                await fetch_kosis_data(ms)
            except Exception as e:  # noqa
                cats["error"] += 1
                return
            cat = categorize(ms.analysis[0])
            cats[cat] += 1
            if cat.startswith("item_ok__") or cat == "no_ev_pure_itmid":
                detail.setdefault(cat, []).append(
                    f"id{row['row_id']}:{row['claim'].get('subject')}/{row['claim'].get('population')}")

    await asyncio.gather(*(run(r) for r in rows))
    print("\n=== 무증거 원인 세분 ===")
    for k, v in cats.most_common():
        print(f"  {k:34} {v}")
    print("\n=== 카테고리별 예시 ===")
    for k, exs in sorted(detail.items(), key=lambda kv: -len(kv[1])):
        print(f"  [{k}] {len(exs)}건")
        for e in exs[:6]:
            print(f"      {e}")


if __name__ == "__main__":
    asyncio.run(main())
