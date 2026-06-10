"""[1-10] 전체 파이프라인 — 문장 1개를 넣고 runner.py 그대로 1→10 을 돈다.

runner.py 의 Pipeline().run(content) 을 그대로 호출한다(부가 로직 없음). 즉 [1]기사확인
→[2]클레임추출(LLM)→[3]정규화→[4]통계표조회→[5]메타·값→[6]랭킹→[7]비교→[8]정합성(LLM)
→[9]판정→[10]설명 까지 실제 모듈 전 과정을 거친다. 이 파일의 자체 코드는 입력 문장 받기
와 결과 저장(md+json)뿐이다.

입력: 명령행 인자 문장(없으면 기본 문장). 결과: tests/results/ 에 md+json (CLAIMS.md 규칙).
키(KOSIS .env / HCX infisical)는 `uv run x` 가 주입.

    uv run x python tests/260610_1-10_full-pipeline_leeaain.py "검증할 문장"
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.pipeline.runner import Pipeline
from src.pipeline.events import ResultEvent, StepEvent

load_dotenv()

OUT_MD = Path(__file__).parent / "results" / "260610_1-10_full-pipeline_leeaain.md"
OUT_JSON = OUT_MD.with_suffix(".json")
# DEFAULT_SENTENCE = "지난달인 2025년 3월의 전체 연령대 실업률은 3%대였다."
DEFAULT_SENTENCE = "지난해(2023년) 한국의 경제성장률은 1.4%에 그쳤다."


async def run(sentence: str):
    """Pipeline().run() 전 과정을 돌리고 (단계로그, master_schema) 반환."""
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


def _save(sentence: str, steps: list, ms) -> None:
    claims = [
        {"claim_type": c.claim_type.value, "subject": c.subject, "population": c.population,
         "value_raw": c.value.raw, "value_llm": c.value.llm_value,
         "period": f"{c.period_type}:{c.period_value.llm_value}", "unit": c.unit}
        for c in ms.claims
    ]
    v = ms.verifications
    results = [] if v is None else [
        {"claim_id": cr.claim_id, "verdict": cr.verdict,
         "claim_value": cr.claim_value, "kosis_value": cr.kosis_value,
         "table": cr.evidence[0].table_name if cr.evidence else None,
         "explanation": cr.explanation}
        for cr in v.claim_results
    ]
    OUT_MD.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps({
        "sentence": sentence,
        "overall_verdict": v.summary.overall_verdict if v else None,
        "claims": claims, "results": results, "steps": steps,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# 260610_1-10_full-pipeline_leeaain",
        "",
        "### 1. 테스트 목적",
        "문장 1개를 넣어 runner.py 전체 파이프라인([1]~[10])이 끝까지 동작하고 "
        "verdict·설명을 산출하는지 확인.",
        "### 2. 검증 대상 모듈",
        "- src/pipeline/runner.py (Pipeline) + src/modules/* [1]~[10] 전 단계",
        "### 3. 도구로만 쓰인 모듈",
        "- 없음 (Pipeline().run 직접 호출)",
        "### 4. 일자 / 작성자",
        "- 2026-06-10 / leeaain",
        "",
        f"### 5. 결과 · 원자료: {OUT_JSON.name}",
        f"- 입력 문장: **{sentence}**",
        f"- overall_verdict: **{v.summary.overall_verdict if v else '—'}**",
        "",
        "**추출 claims**",
        "",
        "| 유형 | subject | population | 값(raw→정규화) | 시점 |",
        "|---|---|---|---|---|",
    ]
    for c in claims:
        md.append(f"| {c['claim_type']} | {c['subject']} | {c['population']} | "
                  f"{c['value_raw']}→{c['value_llm']} | {c['period']} |")
    md += ["", "**검증 결과**", "",
           "| verdict | 주장값 | KOSIS값 | 표 | 설명 |", "|---|---|---|---|---|"]
    for r in results:
        md.append(f"| {r['verdict']} | {r['claim_value']} | {r['kosis_value'] or '—'} | "
                  f"{r['table'] or '—'} | {r['explanation']} |")
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> None:
    sentence = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SENTENCE
    print(f"입력 문장: {sentence}\n")
    steps, ms = asyncio.run(run(sentence))
    _save(sentence, steps, ms)
    v = ms.verifications
    print(f"\noverall_verdict = {v.summary.overall_verdict if v else None}")
    if v:
        for cr in v.claim_results:
            print(f"  [{cr.verdict}] 주장 {cr.claim_value} vs KOSIS {cr.kosis_value}  →  {cr.explanation}")
    print(f"\n저장: {OUT_MD.name}, {OUT_JSON.name}")


if __name__ == "__main__":
    main()
