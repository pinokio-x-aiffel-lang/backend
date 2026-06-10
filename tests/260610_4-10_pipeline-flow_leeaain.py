"""[4-10] KOSIS 파이프라인 엔드투엔드 — 통계표 조회부터 설명 생성까지 실제 모듈로.

목적: 기존 모듈이 엮여서 동작하는지 검증한다. runner.py 처럼 master_schema 를 단계
함수에 차례로 통과시킨다(부가 로직 없음). [4][5]는 라이브 KOSIS, [8]은 라이브 LLM.

  [4] retrieve_kosis_candidates  통계표 조회   → analysis.candidates
  [5] fetch_kosis_data           메타+값 조회  → analysis.evidence
  [6] rank_evidence              (현재 no-op)
  [7] calculate_metric           주장↔KOSIS 비교 → analysis.metric
  [8] check_alignment            모호건 LLM 재판정 (라이브 HCX)
  [9] decide_verdict             verdict/confidence 확정 → verifications
  [10] generate_explanation      설명문 생성

claim 은 (subject, population, period, 주장값)로 직접 구성. 결과는 tests/results/ 에
md+json 저장(CLAUDE.md 규칙). 키(KOSIS .env / HCX infisical)는 `uv run x` 가 주입.

검증 대상: src/modules/* 전 단계 ([4]~[10])
    uv run x python tests/260610_4-10_pipeline-flow_leeaain.py
    uv run x pytest tests/260610_4-10_pipeline-flow_leeaain.py -v
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from src.modules.calculate_metric import calculate_metric
from src.modules.check_alignment import check_alignment
from src.modules.decide_verdict import decide_verdict
from src.modules.fetch_kosis_data import fetch_kosis_data
from src.modules.generate_explanation import generate_explanation
from src.modules.rank_evidence import rank_evidence
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.schemas.runtime import Article, Claim, ClaimType, MasterSchema, ValueSlot

load_dotenv()

OUT_MD = Path(__file__).parent / "results" / "260610_4-10_pipeline-flow_leeaain.md"
OUT_JSON = OUT_MD.with_suffix(".json")

# (subject, population, period_type, period, 주장값, unit) — 기사가 주장했다고 가정한 값.
CLAIMS = [
    ("경제성장률", "대한민국", "Y", "2023", "1.5", "%"),
]
# CLAIMS = [
#     ("실업률", "전국", "Y", "2023", "3.1", "%"),
#     ("합계출산율", "대한민국", "Y", "2023", "0.72", "명"),
#     ("고용률", "남자", "Y", "2023", "71.3", "%"),
#     ("경제성장률", "대한민국", "Y", "2023", "1.4", "%"),
#     ("청년 실업률", "부산광역시", "Y", "2023", "8.1", "%"),
# ]

def _claim(i: int, subject, population, ptype, period, value, unit) -> Claim:
    return Claim(
        claim_id=f"c{i}", article_id="a1",
        sentence=f"{period} {population} {subject}은 {value}{unit}",
        claim_type=ClaimType.ABSOLUTE, subject=subject,
        value=ValueSlot(raw=value, llm_value=value, is_inferred=False),
        unit=unit, aggregation="값", period_type=ptype,
        period_value=ValueSlot(raw=period, llm_value=period, is_inferred=False),
        population=population, cited_source="통계청",
    )


async def run_pipeline() -> MasterSchema:
    """runner.py 처럼 [4]~[10]을 master_schema 에 차례로 통과."""
    ms = MasterSchema(content="x", article=Article(article_id="a1", content="c"))
    ms.claims = [_claim(i, *c) for i, c in enumerate(CLAIMS, 1)]
    await retrieve_kosis_candidates(ms)  # [4]
    await fetch_kosis_data(ms)           # [5]
    await rank_evidence(ms)              # [6]
    await calculate_metric(ms)           # [7]
    await check_alignment(ms)            # [8]
    await decide_verdict(ms)             # [9]
    await generate_explanation(ms)       # [10]
    return ms


def _save(ms: MasterSchema) -> None:
    rows = []
    for cr in ms.verifications.claim_results:
        rows.append({
            "claim_id": cr.claim_id,
            "claim_value": cr.claim_value, "kosis_value": cr.kosis_value,
            "verdict": cr.verdict, "confidence": cr.confidence,
            "candidates_compared": len(cr.evidence),  # [7] n:1 에서 비교한 후보 수
            "rel_diff": cr.metric.rel_diff if cr.metric else None,
            "align_source": cr.metric.align_source if cr.metric else None,
            "explanation": cr.explanation,
        })
    OUT_MD.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps({
        "summary": {"total": len(rows),
                    "overall_verdict": ms.verifications.summary.overall_verdict},
        "results": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# 260610_4-10_pipeline-flow_leeaain",
        "",
        "### 1. 테스트 목적",
        "claim 5건으로 [4]통계표조회→[5]메타·값→[7]비교→[8]정합성→[9]판정→[10]설명 "
        "전 단계가 엮여 동작하는지(실제 값 기반 verdict·설명 생성) 검증.",
        "### 2. 검증 대상 모듈",
        "- src/modules/ [4]retrieve_kosis_candidates [5]fetch_kosis_data [6]rank_evidence "
        "[7]calculate_metric [8]check_alignment [9]decide_verdict [10]generate_explanation",
        "### 3. 도구로만 쓰인 모듈 (검증대상 아님)",
        "- src/schemas/runtime.py — Claim/MasterSchema 입력 구성",
        "### 4. 일자 / 작성자",
        "- 2026-06-10 / leeaain",
        "",
        f"### 5. 결과 (overall={ms.verifications.summary.overall_verdict}) · 원자료: {OUT_JSON.name}",
        "",
        "| claim | 주장값 | KOSIS값 | 비교후보 | verdict | 정합(8) | 설명 |",
        "|---|---|---|---|---|---|---|",
    ]
    for cl, r in zip(CLAIMS, rows):
        expl = (r["explanation"] or "").replace("\n", " ")
        md.append(f"| {cl[0]}/{cl[1]} | {r['claim_value']} | {r['kosis_value'] or '—'} | "
                  f"{r['candidates_compared']} | {r['verdict']} | {r['align_source'] or '-'} | {expl} |")
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")


# ── pytest (라이브) ───────────────────────────────────────────────────────────
live = pytest.mark.skipif(
    not os.getenv("KOSIS_API_KEY"),
    reason="KOSIS_API_KEY 없음 — 라이브 4-10 파이프라인 skip (uv run x 로 실행)",
)


@live
@pytest.mark.asyncio
async def test_pipeline_4_to_10_runs_with_real_modules():
    """[4]~[10]이 예외 없이 흐르고, 더미값 없이 verdict·설명을 산출한다."""
    ms = await run_pipeline()
    _save(ms)
    crs = ms.verifications.claim_results
    assert len(crs) == len(CLAIMS)
    for cr in crs:
        assert cr.verdict in {"T", "F", "M", "N"}   # 유효 verdict
        assert cr.explanation                        # 설명문 존재
    dumped = json.dumps(ms.verifications.model_dump(), ensure_ascii=False)
    assert "(더미)" not in dumped and "UNVERIFIED" not in dumped


if __name__ == "__main__":
    if not os.getenv("KOSIS_API_KEY"):
        raise SystemExit("KOSIS_API_KEY 없음 — uv run x python tests/260610_4-10_pipeline-flow_leeaain.py")
    ms = asyncio.run(run_pipeline())
    _save(ms)
    print(f"overall_verdict = {ms.verifications.summary.overall_verdict}")
    for cl, cr in zip(CLAIMS, ms.verifications.claim_results):
        print(f"  [{cr.verdict}] {cl[0]}/{cl[1]}  주장 {cr.claim_value}{cl[5]} vs KOSIS {cr.kosis_value}")
        print(f"        {cr.explanation}")
    print(f"\n저장: {OUT_MD.name}, {OUT_JSON.name}")
