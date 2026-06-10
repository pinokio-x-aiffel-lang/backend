"""[4-5] KOSIS 파이프라인 엔드투엔드 테스트 — 통계표 조회 → 메타 조회 → 값 조회.

목적: 기존 모듈이 엮여서 실제로 동작하는지 검증한다(runner.py 와 같은 형태로 master_schema 를
단계 함수에 통과시킨다). 부가 로직 없이 단계 모듈만 호출한다.

  [4] retrieve_kosis_candidates(ms)  통계표 조회 → analysis.candidates
  [5] fetch_kosis_data(ms)           메타 조회(map_claim_to_cell→fetch_table_metadata)
                                     + 값 조회(fetch_cell_with_retry) → analysis.evidence

입력: tests/data_KOSIS_(2)통계표메타데이터조회_30개.txt (줄당 'subject, population').
      시점은 claim 에 없어 연간 2023(Y)로 고정(테스트 기본값).
결과: tests/results/ 에 md+json 저장(CLAUDE.md 규칙).

검증 대상: src/modules/retrieve_kosis_candidates.py, src/modules/fetch_kosis_data.py
    uv run x python tests/260610_4-5_kosis-pipeline_leeaain.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from src.modules.fetch_kosis_data import fetch_kosis_data
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.schemas.runtime import Claim, ClaimType, MasterSchema, ValueSlot

load_dotenv()

DATA = Path(__file__).parent / "data_KOSIS_(2)통계표메타데이터조회_30개.txt"
OUT_MD = Path(__file__).parent / "results" / "260610_4-5_kosis-pipeline_leeaain.md"
OUT_JSON = OUT_MD.with_suffix(".json")
PERIOD, PERIOD_TYPE = "2023", "Y"  # 시점 기본값(claim 에 시점 없음)


def _claim(i: int, subject: str, population: str) -> Claim:
    slot = ValueSlot(raw="", llm_value="", is_inferred=False)
    return Claim(
        claim_id=f"c{i}", article_id="kw", sentence=f"{subject} {population}",
        claim_type=ClaimType.VERIFIABLE, subject=subject, value=slot,
        unit="", aggregation="", period_type=PERIOD_TYPE,
        period_value=ValueSlot(raw=PERIOD, llm_value=PERIOD, is_inferred=False),
        population=population, cited_source="",
    )


async def main() -> None:
    pairs = []
    for ln in DATA.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        subj, _, pop = ln.partition(",")
        pairs.append((subj.strip(), pop.strip()))

    ms = MasterSchema(content="kw")
    ms.claims = [_claim(i, s, p) for i, (s, p) in enumerate(pairs, 1)]

    await retrieve_kosis_candidates(ms)  # [4] 통계표 조회
    await fetch_kosis_data(ms)           # [5] 메타 조회 + 값 조회

    rows = []
    for (subj, pop), an in zip(pairs, ms.analysis):
        ev = an.evidence
        rows.append({
            "subject": subj, "population": pop,
            "hits": an.kosis_search.hits,
            "value": ev.value if ev else None,
            "unit": ev.unit if ev else None,
            "tbl_id": ev.kosis_tbl_id if ev else None,
            "table_name": ev.table_name if ev else None,
            "match_source": ev.match_source if ev else None,
            "population_fallback": ev.population_fallback if ev else None,
            "fetch_error": an.kosis_query.error_msg,
        })

    got = sum(1 for r in rows if r["value"] is not None)
    fb = sum(1 for r in rows if r["population_fallback"])
    OUT_MD.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(
        json.dumps({"period": f"{PERIOD}({PERIOD_TYPE})",
                    "summary": {"total": len(rows), "value_ok": got, "population_fallback": fb},
                    "results": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# 260610_4-5_kosis-pipeline_leeaain",
        "",
        "### 1. 테스트 목적",
        "subject·population 30건으로 [4]통계표조회 → [5]메타조회+값조회 파이프라인이 "
        "엮여서 동작하는지(셀 값 확보) 검증. 시점은 2023(Y) 고정.",
        "### 2. 검증 대상 모듈",
        "- src/modules/retrieve_kosis_candidates.py — retrieve_kosis_candidates [4]",
        "- src/modules/fetch_kosis_data.py — fetch_kosis_data [5] (메타+값)",
        "### 3. 도구로만 쓰인 모듈 (검증대상 아님)",
        "- src/schemas/runtime.py — Claim/MasterSchema 입력 구성",
        "### 4. 일자 / 작성자",
        "- 2026-06-10 / leeaain",
        "",
        f"### 5. 결과 (값 확보 {got}/{len(rows)} · 모집단 폴백 {fb}) · 원자료: {OUT_JSON.name}",
        "",
        "| subject | population | 건수 | 값 | 표 | 매칭 | 폴백 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        val = f"{r['value']}{r['unit'] or ''}" if r["value"] is not None else "—"
        src = r["match_source"] or ""
        fbm = "fallback" if r["population_fallback"] else ""
        tbl = r["tbl_id"] or (r["fetch_error"] or "")
        md.append(f"| {r['subject']} | {r['population']} | {r['hits']} | {val} | {tbl} | {src} | {fbm} |")
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"값 확보 {got}/{len(rows)}  (모집단 폴백 {fb})")
    for r in rows:
        val = f"{r['value']}{r['unit'] or ''}" if r["value"] is not None else "—"
        tag = f" [{r['match_source']}{'·fallback' if r['population_fallback'] else ''}]" if r["value"] is not None else ""
        print(f"  {r['subject']}/{r['population']} → {val}  ({r['tbl_id'] or r['fetch_error']}){tag}")
    print(f"\n저장: {OUT_MD.name}, {OUT_JSON.name}")


if __name__ == "__main__":
    asyncio.run(main())
