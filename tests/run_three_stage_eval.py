"""KOSIS 단계별 평가 — 실제 파이프라인 모듈만 호출(독자 로직 없음).

원칙: 테스트는 '값을 더 잘 얻는' 로직을 자체로 두지 않는다.
실제 파이프라인이 쓰는 함수만 호출해 결과·시간을 측정한다.
(테스트 점수를 좋게 만드는 게 목적이 아니다.)

실제 KOSIS 경로는 모듈 2개다(메타 조회는 값 조회 안에 포함):
  [1] retrieve_kosis_candidates : 통계표 조회(search_tables)        → analysis.candidates
  [2] fetch_kosis_data          : 메타 조회(resolve→fetch_meta_item)
                                  + 값 조회(fetch_cell_with_retry)  → analysis.evidence

claim 이 있어야 값 조회가 실제 경로를 탄다. 그래서 claim-driven 이다.
각 단계 시간은 모듈이 schema 에 기록한 duration_ms 를 그대로 읽는다.

결과는 tests/results/ 에 JSON 으로 저장한다.

    uv run x python tests/run_three_stage_eval.py
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
from pathlib import Path

from dotenv import load_dotenv

from src.modules.fetch_kosis_data import fetch_kosis_data
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.schemas.runtime import Claim, ClaimType, MasterSchema, ValueSlot

load_dotenv()  # KOSIS_API_KEY 는 .env (resolve_api_key 와 동일 경로)

OUT_DIR = Path(__file__).parent / "results"
DATE = "260609"

# 평가용 claim 셋 (subject/population/period). 국내·국제·연령축 섞음.
CLAIMS = [
    ("고용률", "청년", "Y", "2023"),       # 연령축 동의어(청년→15-29세)
    ("실업률", "전국", "Y", "2023"),       # 국내 시도축
    ("합계출산율", "전국", "Y", "2020"),    # 국제 국가축 동의어(전국→대한민국)
    ("혼인", "전국", "Y", "2020"),         # 국내
    ("경제성장률", "전국", "Y", "2022"),    # 국내
    ("사망원인", "전국", "Y", "2020"),     # 다축
    ("고령인구", "전국", "Y", "2020"),     # 고령 동의어
    ("소비자물가지수", "전국", "Y", "2022"),
]


def _claim(i: int, subject: str, population: str, se: str, period: str) -> Claim:
    return Claim(
        claim_id=f"c{i}", article_id="eval", sentence=f"{period} {population} {subject}",
        claim_type=ClaimType.ABSOLUTE,
        subject=subject, value=ValueSlot(raw="", llm_value="", is_inferred=False),
        unit="", aggregation="", period_type=se,
        period_value=ValueSlot(raw=period, llm_value=period, is_inferred=False),
        population=population, cited_source="",
    )


async def main() -> None:
    ms = MasterSchema(content="eval")
    ms.claims = [_claim(i, *c) for i, c in enumerate(CLAIMS, 1)]

    t0 = time.perf_counter()
    await retrieve_kosis_candidates(ms)   # [1] 통계표 조회 (실제 모듈)
    t1 = time.perf_counter()
    await fetch_kosis_data(ms)            # [2] 메타+값 조회 (실제 모듈)
    t2 = time.perf_counter()

    # 모듈이 기록한 단계별 소요시간(claim별)을 읽는다.
    search_ms = [a.kosis_search.duration_ms for a in ms.analysis]
    fetch_ms = [a.kosis_query.duration_ms for a in ms.analysis]

    rows = []
    for claim, a in zip(ms.claims, ms.analysis):
        ev = a.evidence
        rows.append({
            "claim_id": claim.claim_id, "subject": claim.subject,
            "population": claim.population, "period": claim.period_value.llm_value,
            "search_hits": a.kosis_search.hits,
            "selected_tbl": a.kosis_search.selected_tbl_id,
            "value": ev.value if ev else None,
            "unit": ev.unit if ev else None,
            "tbl_id": ev.kosis_tbl_id if ev else None,
            "match_source": ev.match_source if ev else None,
            "population_fallback": ev.population_fallback if ev else None,
            "fetch_success": a.kosis_query.success,
            "fetch_error": a.kosis_query.error_msg,
        })

    ok = sum(1 for r in rows if r["value"] is not None)
    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / f"{DATE}_파이프라인_kosis.json"
    path.write_text(json.dumps({
        "claims": len(rows), "value_ok": ok,
        "timing": {
            "stage1_retrieve_total_s": round(t1 - t0, 2),
            "stage2_fetch_total_s": round(t2 - t1, 2),
            "search_ms_avg": round(statistics.mean(search_ms)) if search_ms else 0,
            "fetch_ms_avg": round(statistics.mean(fetch_ms)) if fetch_ms else 0,
        },
        "results": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== KOSIS 파이프라인 평가 (실제 모듈만 호출) ===")
    for r in rows:
        v = f"{r['value']}{r['unit'] or ''}" if r["value"] is not None else "실패"
        src = f" [{r['match_source']}{'·fallback' if r['population_fallback'] else ''}]" if r["value"] is not None else ""
        print(f"  {r['subject']}/{r['population']}/{r['period']} → {v}  ({r['tbl_id']}){src}")
    print(f"\n값 확보 {ok}/{len(rows)}")
    print(f"[1] retrieve_kosis_candidates 총 {t1 - t0:.2f}s  "
          f"(검색 평균 {round(statistics.mean(search_ms))}ms/claim)")
    print(f"[2] fetch_kosis_data         총 {t2 - t1:.2f}s  "
          f"(메타+값 평균 {round(statistics.mean(fetch_ms))}ms/claim)")
    print(f"\n저장: {path}")
    print("[참고] 메타 조회는 실제 파이프라인에서 fetch_kosis_data 내부 resolve "
          "(fetch_meta_item ITM)에 포함 — 독립 단계가 아님.")


if __name__ == "__main__":
    asyncio.run(main())
