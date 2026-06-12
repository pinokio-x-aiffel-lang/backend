"""[10] generate_explanation 견고성 테스트 — 다양한 verdict 분포에서 종합 의견 품질 확인.

실행: infisical run -- uv run python tests/260612_10_generate-explanation-robustness_innnn.py

여러 시나리오(전부 일치 / 전부 불일치 / 전부 검증불가 / 단일 / 대량 혼합)를 각각
[9] 산출물처럼 조립해 generate_explanation 을 호출하고, LLM 종합 의견이 각 분포에서
판정과 일관되게(특히 F를 '정확'으로, M을 '수치 차이'로 오인하지 않게) 나오는지 본다.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from src.modules.generate_explanation import _claim_line, generate_explanation
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
STEM = "260612_10_generate-explanation-robustness_innnn_01"  # _01: [검증불가]=오류 아님 규칙 추가 후

# (verdict, subject, unit, period, population, claim_value, kosis_value, mismatch_type)
SCENARIOS: list[dict] = [
    {"name": "전부 일치 (T×3)", "rows": [
        ("T", "합계출산율", "명", "2024", "대한민국", "0.72", "0.72", None),
        ("T", "경제성장률", "%", "2023", "대한민국", "2.0", "2.0", None),
        ("T", "수출액", "억달러", "2023", "대한민국", "6835", "6835", None),
    ]},
    {"name": "전부 불일치 (F×3, 사유 다양)", "rows": [
        ("F", "청년 실업률", "%", "2023", "15~29세", "6.5", "7.1", "magnitude"),
        ("F", "GDP 성장률", "%", "2023", "대한민국", "2.1", "-0.5", "direction"),
        ("F", "소비자물가 상승률", "%", "2023", "대한민국", "3.2", "2.8", "period"),
    ]},
    {"name": "전부 검증불가 (N×3)", "rows": [
        ("N", "노인 빈곤율", "%", "2023", "65세 이상", "45.0", None, None),
        ("N", "체감 경기지수", "포인트", "2024", "대한민국", "70", None, None),
        ("N", "주거 만족도", "점", "2023", "대한민국", "3.5", None, None),
    ]},
    {"name": "단일 불일치 (F×1)", "rows": [
        ("F", "합계출산율", "명", "2024", "대한민국", "0.65", "0.72", "magnitude"),
    ]},
    {"name": "대량 혼합 (2T·2F·1M·1N)", "rows": [
        ("T", "합계출산율", "명", "2024", "대한민국", "0.72", "0.72", None),
        ("T", "경제성장률", "%", "2023", "대한민국", "2.0", "2.0", None),
        ("F", "청년 실업률", "%", "2023", "15~29세", "6.5", "7.1", "magnitude"),
        ("F", "수출액", "억달러", "2023", "대한민국", "7000", "6835", "magnitude"),
        ("M", "주당 평균 근로시간", "시간", "2024", "임금근로자", "38.8", "38.8", "population"),
        ("N", "노인 빈곤율", "%", "2023", "65세 이상", "45.0", None, None),
    ]},
]


def _vs(v: str) -> ValueSlot:
    return ValueSlot(raw=v, llm_value=v, is_inferred=False)


def _build_master(rows: list[tuple]) -> MasterSchema:
    claims, results = [], []
    counts = {"T": 0, "F": 0, "M": 0, "N": 0}
    for i, (verdict, subject, unit, period, pop, cval, kval, mismatch) in enumerate(rows):
        cid = f"c{i}"
        claims.append(Claim(
            claim_id=cid, article_id="art", sentence=f"{pop} {subject}은 {cval}{unit}이다.",
            claim_type=ClaimType.ABSOLUTE, subject=subject, value=_vs(cval), unit=unit,
            aggregation="", period_type="Y", period_value=_vs(period),
            population=pop, cited_source="통계청",
        ))
        ev = [] if kval is None else [Evidence(
            claim_id=cid, source="KOSIS", subject=subject, unit=unit, period_type="Y",
            period=period, population=pop, table_name=f"{subject} 통계표", value=float(kval),
        )]
        results.append(ClaimResult(
            claim_id=cid, verdict=verdict, claim_value=cval, kosis_value=kval,
            mismatch_type=mismatch, evidence=ev,
        ))
        counts[verdict] += 1

    total = len(rows)
    resolved = counts["T"] + counts["F"] + counts["M"]
    summary = VerificationSummary(
        total_claims=total, verdict_counts=counts,
        overall_confidence=(counts["T"] / resolved) if resolved else 0.0,
        coverage=(resolved / total) if total else 0.0,
    )
    return MasterSchema(claims=claims, verifications=Verifications(
        summary=summary, claim_results=results,
    ))


async def _run_one(scenario: dict) -> dict:
    master = _build_master(scenario["rows"])
    cmap = {c.claim_id: c for c in master.claims}
    # LLM 에 실제로 들어간 주장별 줄(투명성용)
    llm_input_lines = [_claim_line(r, cmap.get(r.claim_id))
                       for r in master.verifications.claim_results]
    await generate_explanation(master)
    s = master.verifications.summary
    return {
        "name": scenario["name"],
        "verdict_counts": s.verdict_counts,
        "overall_confidence": s.overall_confidence,
        "llm_input_lines": llm_input_lines,
        "overall_opinion": s.overall_opinion,
    }


async def _run_all() -> dict:
    out = []
    for sc in SCENARIOS:
        out.append(await _run_one(sc))
    return {"stem": STEM, "ran_at": datetime.now(timezone.utc).isoformat(), "scenarios": out}


def _write_md(data: dict) -> str:
    lines = [
        f"# [10] generate_explanation 견고성 테스트 — {data['ran_at'][:10]}",
        "",
        "1. **테스트 목적**: 다양한 verdict 분포에서 종합 의견이 판정과 일관되게 나오는지(견고성) 확인",
        "2. **검증 대상 모듈**: `src/modules/generate_explanation.py`",
        "3. **도구로만 쓰인 모듈**: `src/llm/*`(HCX-005), `src/prompts/prompts.py`, `src/schemas/runtime.py`",
        "4. **일자/작성자**: 2026-06-12 / innnn",
        "",
        f"- 원자료(JSON): `tests/results/{STEM}.json`",
        "",
    ]
    for sc in data["scenarios"]:
        conf = round(sc["overall_confidence"] * 100)
        lines += [
            f"## {sc['name']}",
            "",
            f"- verdict_counts: `{sc['verdict_counts']}` / 사실 비율: **{conf}%**",
            "- LLM 입력(주장별 줄):",
            "```",
            *sc["llm_input_lines"],
            "```",
            "- **종합 의견**:",
            "",
            f"> {sc['overall_opinion']}",
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    data = asyncio.run(_run_all())
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"{STEM}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (RESULTS_DIR / f"{STEM}.md").write_text(_write_md(data), encoding="utf-8")
    for sc in data["scenarios"]:
        print(f"[{sc['name']}] conf={round(sc['overall_confidence']*100)}%")
    print(f"\n[저장] tests/results/{STEM}.json / .md")


if __name__ == "__main__":
    main()
