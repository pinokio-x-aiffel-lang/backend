"""[4] 통계표 조회 테스트 — 키워드 30개로 retrieve_kosis_candidates 가 응답을 받아오는지 확인.

입력: tests/data_KOSIS_(1)통계표조회_30개.txt (키워드 1줄당 1개)
각 키워드를 claim.subject 로 넣어 4단계 모듈 retrieve_kosis_candidates 를 실제 배선대로
돌린다. 키워드별로 통계표 후보를 성공적으로 받아오는지(success==1 & hits>0) 본다.
응답은 tests/results/ 에 md+json 저장.

검증 대상: src/modules/retrieve_kosis_candidates.py
    uv run x python tests/260610_4_kosis-search-keywords_leeaain.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.schemas.runtime import Claim, ClaimType, MasterSchema, ValueSlot

load_dotenv()

KEYWORDS = Path(__file__).parent / "data_KOSIS_(1)통계표조회_30개.txt"
OUT_MD = Path(__file__).parent / "results" / "260610_4_kosis-search-keywords_leeaain.md"
OUT_JSON = OUT_MD.with_suffix(".json")


def _claim(i: int, keyword: str) -> Claim:
    slot = ValueSlot(raw="", llm_value="", is_inferred=False)
    return Claim(
        claim_id=f"c{i}", article_id="kw", sentence=keyword,
        claim_type=ClaimType.VERIFIABLE, subject=keyword, value=slot,
        unit="", aggregation="", period_type="Y", period_value=slot,
        population="", cited_source="",
    )


async def main() -> None:
    keywords = [ln.strip() for ln in KEYWORDS.read_text(encoding="utf-8").splitlines() if ln.strip()]
    ms = MasterSchema(content="kw")
    ms.claims = [_claim(i, kw) for i, kw in enumerate(keywords, 1)]
    await retrieve_kosis_candidates(ms)  # [4] 실제 모듈

    rows = []
    for kw, an in zip(keywords, ms.analysis):
        s = an.kosis_search
        rows.append({
            "keyword": kw, "ok": s.success == 1 and s.hits > 0, "hits": s.hits,
            "top_tbl_id": s.selected_tbl_id, "top_tbl_nm": s.selected_tbl_name,
            "candidates": [{"org_id": c.org_id, "tbl_id": c.tbl_id, "tbl_nm": c.tbl_nm}
                           for c in an.candidates],
            "error": s.error_msg,
        })

    ok = sum(1 for r in rows if r["ok"])
    OUT_MD.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(
        json.dumps({"summary": {"total": len(rows), "ok": ok}, "results": rows},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# 260610_4_kosis-search-keywords_leeaain",
        "",
        "### 1. 테스트 목적",
        "키워드 30개를 subject 로 넣어 [4] 통계표 조회(retrieve_kosis_candidates)가 "
        "통계표 후보를 받아오는지(success==1 & hits>0) 확인.",
        "### 2. 검증 대상 모듈",
        "- src/modules/retrieve_kosis_candidates.py — retrieve_kosis_candidates",
        "### 3. 도구로만 쓰인 모듈 (검증대상 아님)",
        "- src/kosis/search.py — search_tables(통합검색 호출)",
        "- src/schemas/runtime.py — Claim/MasterSchema 등 입력 구성",
        "### 4. 일자 / 작성자",
        "- 2026-06-10 / leeaain",
        "",
        f"### 5. 결과 (성공 {ok}/{len(rows)}) · 원자료: {OUT_JSON.name}",
        "",
        "| 키워드 | 성공 | 건수 | RANK 1 통계표 |",
        "|---|---|---|---|",
    ]
    for r in rows:
        mark = "✓" if r["ok"] else "✗"
        top = f"{r['top_tbl_id']} {r['top_tbl_nm']}" if r["top_tbl_id"] else (r["error"] or "-")
        md.append(f"| {r['keyword']} | {mark} | {r['hits']} | {top} |")
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"통계표 조회 성공 {ok}/{len(rows)}")
    for r in rows:
        mark = "✓" if r["ok"] else "✗"
        print(f"  {mark} {r['keyword']}: {r['hits']}건  → {r['top_tbl_id'] or ''} {r['top_tbl_nm'] or ''}")
    print(f"\n저장: {OUT_MD.name}, {OUT_JSON.name}")


if __name__ == "__main__":
    asyncio.run(main())
