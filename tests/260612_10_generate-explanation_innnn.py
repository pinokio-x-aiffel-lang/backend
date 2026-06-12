"""[10] generate_explanation 단독 테스트 — 기사 단위 LLM 종합 의견 품질 확인.

실행: infisical run -- uv run python tests/260612_10_generate-explanation_innnn.py
  (CLOVASTUDIO_API_KEY 가 Infisical 로 주입돼야 실제 HCX 호출이 된다)

[9]까지 끝난 상태를 모사한 MasterSchema(claim_results 에 T/F/M/N 혼합)를 만들어
generate_explanation 을 호출하고, claim별 템플릿 설명 + 기사 단위 종합 의견을
tests/results/ 에 json·md 로 남긴다.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from src.modules.generate_explanation import generate_explanation
from src.schemas.runtime import (
    Claim,
    ClaimResult,
    ClaimType,
    Evidence,
    MasterSchema,
    ValueSlot,
    VerificationSummary,
    Verifications,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
STEM = "260612_10_generate-explanation_innnn_02"  # _02: M 뉘앙스(수치 일치=/≠) 강화 후 재실행


def _vs(raw: str, llm: str) -> ValueSlot:
    return ValueSlot(raw=raw, llm_value=llm, is_inferred=False)


def _claim(cid, subject, unit, period, population, value_raw, value_llm) -> Claim:
    return Claim(
        claim_id=cid,
        article_id="art-1",
        sentence=f"{population} {subject}은(는) {value_raw}이다.",
        claim_type=ClaimType.ABSOLUTE,
        subject=subject,
        value=_vs(value_raw, value_llm),
        unit=unit,
        aggregation="",
        period_type="Y",
        period_value=_vs(period, period),
        population=population,
        cited_source="통계청",
    )


def _evidence(cid, subject, unit, period, population, table_name, value) -> Evidence:
    return Evidence(
        claim_id=cid, source="KOSIS", subject=subject, unit=unit,
        period_type="Y", period=period, population=population,
        table_name=table_name, value=value,
    )


def _build_master() -> MasterSchema:
    claims = [
        _claim("c1", "청년 실업률", "%", "2023", "15~29세", "6.5%", "6.5"),
        _claim("c2", "합계출산율", "명", "2024", "대한민국", "0.72명", "0.72"),
        _claim("c3", "주당 평균 근로시간", "시간", "2024", "임금근로자", "38.8시간", "38.8"),
        _claim("c4", "노인 빈곤율", "%", "2023", "65세 이상", "45.0%", "45.0"),
    ]
    results = [
        # F — 수치 자체가 공식치와 다름
        ClaimResult(
            claim_id="c1", verdict="F", claim_value="6.5", kosis_value="7.1",
            mismatch_type="magnitude",
            evidence=[_evidence("c1", "청년 실업률", "%", "2023", "15~29세", "경제활동인구조사", 7.1)],
        ),
        # T — 일치
        ClaimResult(
            claim_id="c2", verdict="T", claim_value="0.72", kosis_value="0.72",
            evidence=[_evidence("c2", "합계출산율", "명", "2024", "대한민국", "인구동향조사", 0.72)],
        ),
        # M — 수치는 맞으나 표현 왜곡(모집단 오도)
        ClaimResult(
            claim_id="c3", verdict="M", claim_value="38.8", kosis_value="38.8",
            mismatch_type="population",
            evidence=[_evidence("c3", "주당 평균 근로시간", "시간", "2024", "임금근로자", "근로형태별 근로실태조사", 38.8)],
        ),
        # N — KOSIS 데이터 없음
        ClaimResult(
            claim_id="c4", verdict="N", claim_value="45.0", kosis_value=None,
            evidence=[],
        ),
    ]
    # [9] decide_verdict 산출물 모사: 분포·지표를 직접 채운다(verdict_counts 배선 검증).
    counts = {"T": 1, "F": 1, "M": 1, "N": 1}
    resolved = counts["T"] + counts["F"] + counts["M"]
    summary = VerificationSummary(
        total_claims=len(results),
        verdict_counts=counts,
        overall_confidence=counts["T"] / resolved,   # T/(T+F+M)
        coverage=resolved / len(results),
    )
    return MasterSchema(
        claims=claims,
        verifications=Verifications(summary=summary, claim_results=results),
    )


async def _run() -> dict:
    master = _build_master()
    await generate_explanation(master)
    v = master.verifications
    return {
        "stem": STEM,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "verdict_counts": v.summary.verdict_counts,
        "overall_confidence": v.summary.overall_confidence,
        "coverage": v.summary.coverage,
        "overall_opinion": v.summary.overall_opinion,
        "claim_results": [
            {
                "claim_id": r.claim_id,
                "verdict": r.verdict,
                "mismatch_type": r.mismatch_type,
                "claim_value": r.claim_value,
                "kosis_value": r.kosis_value,
                "explanation": r.explanation,
            }
            for r in v.claim_results
        ],
    }


def _write_md(data: dict) -> str:
    lines = [
        f"# [10] generate_explanation 종합 의견 테스트 — {data['ran_at'][:10]}",
        "",
        "1. **테스트 목적**: [10] generate_explanation 이 생성하는 기사 단위 LLM 종합 의견의 품질 확인",
        "2. **검증 대상 모듈**: `src/modules/generate_explanation.py` (특히 `_generate_opinion`)",
        "3. **도구로만 쓰인 모듈**: `src/llm/*`(LlmCaller·HCX-005), `src/prompts/prompts.py`, `src/schemas/runtime.py`",
        "4. **일자/작성자**: 2026-06-12 / innnn",
        "",
        f"- 원자료(JSON): `tests/results/{STEM}.json`",
        f"- verdict_counts: **{data['verdict_counts']}** / 사실 비율(overall_confidence): "
        f"**{round(data['overall_confidence'] * 100)}%**",
        "",
        "## 기사 단위 종합 의견 (LLM)",
        "",
        f"> {data['overall_opinion']}",
        "",
        "## claim별 템플릿 설명",
        "",
        "| claim | verdict | explanation |",
        "|---|---|---|",
    ]
    for r in data["claim_results"]:
        expl = r["explanation"].replace("|", "\\|")
        lines.append(f"| {r['claim_id']} | {r['verdict']} | {expl} |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    data = asyncio.run(_run())
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"{STEM}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (RESULTS_DIR / f"{STEM}.md").write_text(_write_md(data), encoding="utf-8")
    print("=== overall_opinion ===")
    print(data["overall_opinion"])
    print(f"\n[저장] tests/results/{STEM}.json / .md")


if __name__ == "__main__":
    main()
