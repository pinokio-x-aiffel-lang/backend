"""[4+5 대안] map_claim_via_meta smoke test.

두 모드:
  --mock : LLM 선택을 정답으로 주입 → KOSIS 검색·메타·조회·YoY 배관을 실제 KOSIS 로 검증
           (CLOVASTUDIO_API_KEY 없이도 실행 가능. KOSIS_API_KEY 만 필요.)
  (기본): HCX-007 실호출 — CLOVASTUDIO_API_KEY 가 있어야 동작(Langfuse 트레이싱).

사용:
  PYTHONPATH=. python benchmark/260618_4~5_kosis-meta-path_innnn/260618_4~5_kosis-meta-path_innnn.py --mock
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from src.modules import map_claim_via_meta as M
from src.schemas.runtime import Claim, ClaimType, MasterSchema, ValueSlot

OUT = Path(__file__).with_name("260618_4~5_kosis-meta-path_innnn_result.json")


def _vs(v: str) -> ValueSlot:
    return ValueSlot(raw=v, llm_value=v, is_inferred=False)


def _claim(cid, subject, value, period_type, period, unit, population, ctype):
    return Claim(
        claim_id=cid, article_id="smoke", sentence=subject,
        claim_type=ctype, subject=subject, value=_vs(value), unit=unit,
        aggregation="", period_type=period_type, period_value=_vs(period),
        population=population, cited_source="통계청",
    )


# 260617 10건 중 대표 5건(주제·연산 다양 + 숨은 C1축·지수 YoY 포함). 기대값은 실측.
CASES = [
    {"claim": _claim("c1", "취업자 수", "28589", "M", "2025-03", "천명", "전체", ClaimType.ABSOLUTE),
     "expect": 28589,
     "mock": {"tbl_id": "DT_1DA7001S", "itm_id": "T30",
              "axis_codes": [{"obj_id": "B", "code": "0"}], "abstain": False}},
    {"claim": _claim("c2", "청년 실업률", "7.5", "M", "2025-03", "%", "청년 15-29세", ClaimType.ABSOLUTE),
     "expect": 7.5,
     "mock": {"tbl_id": "DT_1DA7102S", "itm_id": "T80",
              "axis_codes": [{"obj_id": "B", "code": "0"}, {"obj_id": "G", "code": "75"}],
              "abstain": False}},
    {"claim": _claim("c3", "소비자물가 상승률", "2.2", "M", "2025-01", "%", "전국", ClaimType.CHANGE_RATE),
     "expect": 2.2,
     "mock": {"tbl_id": "DT_1J22003", "itm_id": "T",
              "axis_codes": [{"obj_id": "C", "code": "T10"}], "abstain": False}},
    {"claim": _claim("c4", "석유류 물가 상승률", "6.3", "M", "2025-02", "%", "전국", ClaimType.CHANGE_RATE),
     "expect": 6.3,
     "mock": {"tbl_id": "DT_1J22002", "itm_id": "T",
              "axis_codes": [{"obj_id": "C", "code": "T10"}, {"obj_id": "J", "code": "2125"}],
              "abstain": False}},
    {"claim": _claim("c5", "제조업 취업자 수", "4414", "M", "2025-06", "천명", "전체", ClaimType.ABSOLUTE),
     "expect": 4414,
     "mock": {"tbl_id": "DT_1DA7E43S_NEW", "itm_id": "T30",
              "axis_codes": [{"obj_id": "I", "code": "10"}, {"obj_id": "K", "code": "00"}],
              "abstain": False}},
]


async def run(mock: bool) -> list[dict]:
    api_key = M.resolve_api_key()
    out = []
    for case in CASES:
        claim = case["claim"]
        if mock:
            # LLM 선택을 정답으로 주입 — 검색/메타/조회/YoY 배관만 검증.
            hits = await asyncio.to_thread(M.search_tables, claim.subject, top_n=M.KEYWORD_TOP_N)
            hit = next((h for h in hits if h.tbl_id == case["mock"]["tbl_id"]), None)
            if hit is None:  # 검색 상위에 없으면 직접 메타만 — org 101 고정
                from src.kosis.search import SearchHit
                hit = SearchHit(org_id="101", tbl_id=case["mock"]["tbl_id"], tbl_nm=case["mock"]["tbl_id"])
            meta = await asyncio.to_thread(M.fetch_table_metadata, hit.org_id, hit.tbl_id, api_key)
            ev, q = await asyncio.to_thread(
                M._fetch_selected_cell, claim, hit, meta, case["mock"], api_key
            )
            got = ev.value if ev else None
        else:
            ms = MasterSchema(content="smoke")
            ms.claims = [claim]
            await M.map_claim_via_meta(ms)
            evs = ms.analysis[0].evidences if ms.analysis else []
            got = evs[0].value if evs else None

        exp = case["expect"]
        ok = got is not None and abs(got - exp) <= max(0.05, abs(exp) * 0.001)
        out.append({"claim_id": claim.claim_id, "subject": claim.subject,
                    "tbl": case["mock"]["tbl_id"], "expect": exp, "got": got, "pass": ok})
        print(f"[{'OK ' if ok else 'XX '}] {claim.subject:14} 기대 {exp} → 조회 {got}")
    return out


if __name__ == "__main__":
    mock = "--mock" in sys.argv
    print(f"=== map_claim_via_meta smoke ({'MOCK 배관' if mock else 'HCX 실호출'}) ===")
    results = asyncio.run(run(mock))
    n_ok = sum(r["pass"] for r in results)
    print(f"\n{n_ok}/{len(results)} pass")
    OUT.write_text(json.dumps(
        {"mode": "mock" if mock else "hcx", "pass": n_ok, "total": len(results),
         "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[saved] {OUT}")
