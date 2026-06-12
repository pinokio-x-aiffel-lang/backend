"""[4-5] KOSIS 실조회 검증 — 테이블 찾기·메타데이터·셀 값 조회가 실제로 일어나는지 확인.

runner.py 의 Pipeline().run() 전 과정을 돌린 뒤, 각 claim 의 ClaimAnalysis 에서
KOSIS 단계 내부값을 그대로 꺼내 보여준다. 사용자 요청 출력값:
  - 찾은 테이블 개수 (kosis_search.hits) + 후보 풀 크기(len candidates)
  - 찾은 테이블의 tbl_NM (selected_tbl_name + 후보별 tbl_nm)
  - 메타데이터 objL1 값 (cell_attempts[*].axes 의 첫 분류축 = objL1, evidences[*].classification)
  - 실제 조회된 셀 값 (evidences[*].value) + 셀 조회 로그(kosis_query)

키(KOSIS_API_KEY / HCX)는 `uv run x` 가 infisical 로 주입한다. 반드시:
    uv run x python tests/260612_4-5_kosis-verify_leeaain.py "검증할 문장"
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from src.pipeline.events import ResultEvent, StepEvent
from src.pipeline.runner import Pipeline

OUT_MD = Path(__file__).parent / "results" / "260612_4-5_kosis-verify_leeaain.md"
OUT_JSON = OUT_MD.with_suffix(".json")

# 기본 문장: 과거 시점·구체 수치라 KOSIS 조회가 성공해야 정상(대조군).
DEFAULT_SENTENCE = "지난해(2023년) 한국의 경제성장률은 1.4%에 그쳤다."


async def run(sentence: str):
    steps, ms = [], None
    async for ev in Pipeline().run(sentence):
        if isinstance(ev, StepEvent):
            steps.append({"step": ev.step, "name": ev.name, "status": ev.status,
                          "error": ev.error, "duration_ms": ev.duration_ms})
            print(f"[{ev.step}] {ev.name}: {ev.status}"
                  + (f"  ERROR={ev.error}" if ev.error else ""))
        elif isinstance(ev, ResultEvent):
            ms = ev.master_schema
    return steps, ms


def _claim_map(ms):
    return {c.claim_id: c for c in ms.claims}


def _dump_analysis(ms) -> list[dict]:
    """각 claim 의 KOSIS 단계 내부값을 추출."""
    cmap = _claim_map(ms)
    out = []
    for a in ms.analysis:
        c = cmap.get(a.claim_id)
        ks = a.kosis_search
        # objL1 = 메타데이터 첫 분류축. cell_attempts 의 axes(분류축명→값샘플)에서 첫 축.
        objl1_axes = []
        for ca in a.cell_attempts:
            if ca.axes:
                first_axis = next(iter(ca.axes.items()))  # (축명, [값,...])
                objl1_axes.append({"tbl_id": ca.tbl_id, "tbl_nm": ca.tbl_nm,
                                   "objL1_axis_name": first_axis[0],
                                   "objL1_values": first_axis[1]})
        out.append({
            "claim_id": a.claim_id,
            "subject": c.subject if c else None,
            "population": c.population if c else None,
            "period": f"{c.period_type}:{c.period_value.llm_value}" if c else None,
            "value_raw->llm": f"{c.value.raw}->{c.value.llm_value}" if c else None,
            # ── 찾은 테이블 개수 ──
            "search_query": ks.query,
            "hits(찾은_테이블_개수)": ks.hits,
            "candidate_pool_size": len(a.candidates),
            "search_success": ks.success,
            "search_error_msg": ks.error_msg,
            # ── 찾은 테이블 tbl_NM ──
            "selected_tbl_id": ks.selected_tbl_id,
            "selected_tbl_NM": ks.selected_tbl_name,
            "candidate_tbl_NMs": [{"tbl_id": x.tbl_id, "tbl_nm": x.tbl_nm,
                                   "stat_nm": x.stat_nm, "prd_de": x.prd_de}
                                  for x in a.candidates],
            # ── 메타데이터 objL1 ──
            "objL1_from_metadata": objl1_axes,
            "cell_attempts": [{"tbl_id": ca.tbl_id, "tbl_nm": ca.tbl_nm,
                               "matched": ca.matched, "value": ca.value,
                               "itm_id": ca.itm_id, "axes": ca.axes,
                               "error": ca.error} for ca in a.cell_attempts],
            # ── 실제 조회된 셀 값 ──
            "kosis_query_tbl_id": a.kosis_query.tbl_id,
            "kosis_query_rows": a.kosis_query.rows_returned,
            "kosis_query_success": a.kosis_query.success,
            "kosis_query_params": a.kosis_query.params,
            "kosis_query_error": a.kosis_query.error_msg,
            "evidences": [{"value": e.value, "unit": e.unit, "period": e.period,
                           "table_name": e.table_name, "tbl_id": e.kosis_tbl_id,
                           "itm_id": e.kosis_item_id,
                           "objL_classification": e.classification,
                           "population_fallback": e.population_fallback,
                           "match_source": e.match_source} for e in a.evidences],
        })
    return out


def _print_report(sentence: str, analysis: list[dict], ms) -> None:
    print("\n" + "=" * 70)
    print(f"입력 문장: {sentence}")
    print(f"KOSIS_API_KEY 주입 여부: {'있음' if os.getenv('KOSIS_API_KEY') else '없음(❌ uv run x 미경유?)'}")
    print("=" * 70)
    for i, a in enumerate(analysis, 1):
        print(f"\n── claim {i} [{a['subject']} / {a['population']} / {a['period']}] ──")
        print(f"  검색어: {a['search_query']}  (success={a['search_success']})")
        if a["search_error_msg"]:
            print(f"  ❌ 검색 에러: {a['search_error_msg']}")
        print(f"  ① 찾은 테이블 개수(hits): {a['hits(찾은_테이블_개수)']}  (후보풀 {a['candidate_pool_size']})")
        print(f"  ② 선정 테이블 tbl_NM: {a['selected_tbl_NM']}  (tbl_id={a['selected_tbl_id']})")
        for ct in a["candidate_tbl_NMs"][:5]:
            print(f"       · {ct['tbl_id']}  {ct['tbl_nm']}")
        print(f"  ③ 메타데이터 objL1:")
        if a["objL1_from_metadata"]:
            for o in a["objL1_from_metadata"]:
                vals = ", ".join(o["objL1_values"][:8])
                print(f"       [{o['tbl_nm']}] 축='{o['objL1_axis_name']}' → {vals}")
        else:
            print("       (분류축 없음 — 셀 조회 미수행이거나 단일계열 표)")
        print(f"  ④ 조회된 셀 값(evidences {len(a['evidences'])}건):")
        for e in a["evidences"]:
            print(f"       value={e['value']} {e['unit']}  @{e['period']}  "
                  f"[{e['table_name']}] objL={e['objL_classification']}")
        if not a["evidences"]:
            print(f"       (0건)  kosis_query: tbl={a['kosis_query_tbl_id']} "
                  f"rows={a['kosis_query_rows']} success={a['kosis_query_success']} "
                  f"err={a['kosis_query_error']}")
    v = ms.verifications
    if v:
        print(f"\noverall_verdict = {v.summary.overall_verdict}")
        for cr in v.claim_results:
            print(f"  [{cr.verdict}] 주장 {cr.claim_value!r} vs KOSIS {cr.kosis_value}")


def _save(sentence: str, steps: list, analysis: list[dict], ms) -> None:
    v = ms.verifications
    OUT_MD.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps({
        "sentence": sentence,
        "kosis_api_key_present": bool(os.getenv("KOSIS_API_KEY")),
        "overall_verdict": v.summary.overall_verdict if v else None,
        "analysis": analysis, "steps": steps,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# 260612_4-5_kosis-verify_leeaain",
        "",
        "### 1. 테스트 목적",
        "KOSIS 단계가 실제로 통계표를 찾고(검색), 메타데이터(objL1)를 얻고, 셀 값을 "
        "조회하는지 내부값으로 검증. 사용자 요청: 찾은 테이블 tbl_NM·개수·objL1 출력.",
        "### 2. 검증 대상 모듈",
        "- src/modules/retrieve_kosis_candidates.py [4], src/modules/fetch_kosis_data.py [5]",
        "- src/kosis/ (search·metadata·cell·map_claim_to_cell)",
        "### 3. 도구로만 쓰인 모듈",
        "- src/pipeline/runner.py [1]~[10] 전체 (KOSIS 단계 입력 조성용)",
        "### 4. 일자 / 작성자",
        "- 2026-06-12 / leeaain",
        "",
        f"### 5. 결과 · 원자료: {OUT_JSON.name}",
        f"- 입력 문장: **{sentence}**",
        f"- KOSIS_API_KEY 주입: **{'있음' if os.getenv('KOSIS_API_KEY') else '없음'}**",
        f"- overall_verdict: **{v.summary.overall_verdict if v else '—'}**",
        "",
        "| claim | hits(테이블수) | 선정 tbl_NM | objL1 축 | 조회값(evidence) |",
        "|---|---|---|---|---|",
    ]
    for a in analysis:
        objl1 = "; ".join(f"{o['objL1_axis_name']}={'/'.join(o['objL1_values'][:4])}"
                          for o in a["objL1_from_metadata"]) or "—"
        evid = "; ".join(f"{e['value']}{e['unit']}@{e['period']}" for e in a["evidences"]) or "—"
        md.append(f"| {a['subject']} | {a['hits(찾은_테이블_개수)']} | "
                  f"{a['selected_tbl_NM'] or '—'} | {objl1} | {evid} |")
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> None:
    sentence = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SENTENCE
    print(f"입력 문장: {sentence}\n")
    steps, ms = asyncio.run(run(sentence))
    analysis = _dump_analysis(ms)
    _print_report(sentence, analysis, ms)
    _save(sentence, steps, analysis, ms)
    print(f"\n저장: {OUT_MD.name}, {OUT_JSON.name}")


if __name__ == "__main__":
    main()
