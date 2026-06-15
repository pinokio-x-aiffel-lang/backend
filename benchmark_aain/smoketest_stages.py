"""각 단계 평가셋으로 '실제 모듈을 구동·채점할 수 있는지' 실증(오프라인 가능 단계).

오프라인(LLM/KOSIS 불필요): 7 numeric(compute_absolute) · 9 decide_verdict · 10 템플릿 · 3 룰.
이들을 실제 모듈 함수에 통과시켜 scorable 행 채점 → "테스트 가능" 실증.
LLM/KOSIS 단계(2·4·5·6·8)는 여기서 안 돌림(구동 자체가 API; 캡처로 이미 실행 확인).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.numeric.compare import compute_absolute
from src.modules.decide_verdict import decide_verdict
from src.modules.generate_explanation import _build_explanation
from src.modules.normalize_claim import _parse_value, _normalize_period
from src.schemas.runtime import (
    Article, Claim, ClaimResult, ClaimType, Evidence, MasterSchema,
    MetricResult, ValueSlot, Verdict, VerificationSummary, Verifications,
)

DATA = Path(__file__).resolve().parent / "data"
PFX = "260614_source_from_origin_for_"


def jl(name):
    return [json.loads(l) for l in (DATA / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def _vs(llm):
    return ValueSlot(raw="", llm_value=llm or "", is_inferred=False)


def _claim(cd, ev_period=""):
    return Claim(
        claim_id="c", article_id="a", sentence="", claim_type=ClaimType(cd["claim_type"]),
        subject="x", value=_vs(cd.get("value_llm")), unit=cd.get("unit") or "",
        aggregation="값", period_type="Y", period_value=_vs(cd.get("period_llm")),
        population="x", cited_source="x",
    )


def _evidence(ed):
    return Evidence(
        claim_id="c", source="KOSIS", subject="x", unit=ed.get("unit") or "",
        period_type="Y", period=ed.get("period") or "", population="x",
        value=ed.get("value"), population_fallback=bool(ed.get("population_fallback")),
    )


# ── [7] calculate_metric (numeric, 오프라인) ──
def test7():
    rows = [r for r in jl(f"{PFX}calculate_metric.jsonl") if r.get("scorable") and r.get("evidence")]
    ABS = {"absolute", "verifiable"}
    n = ok = skip_nonabs = 0
    for r in rows:
        gold = r["gold_verdict_stage7"]
        if r["claim"]["claim_type"] not in ABS:
            # 7단계는 비절대형을 NEI 로 둠 → gold 가 N 이면 일치
            pred = "N"
            skip_nonabs += 1
        else:
            m = compute_absolute(_claim(r["claim"]), _evidence(r["evidence"]))
            pred = m.verdict.value if m.verdict else "N"
        n += 1
        ok += (pred == gold)
    return f"scorable {n} 채점 | verdict 정확도 {ok}/{n} = {ok/n:.0%} | 비절대형 {skip_nonabs}건은 NEI 처리"


# ── [9] decide_verdict (결정적, 오프라인) ──
async def _run9():
    rows = jl(f"{PFX}decide_verdict.jsonl")
    n = ok = 0
    for r in rows:
        crs = [ClaimResult(claim_id=str(i), metric=MetricResult(operation="x", verdict=Verdict(c["verdict"])))
               for i, c in enumerate(r["claim_results"])]
        ms = MasterSchema(verifications=Verifications(
            summary=VerificationSummary(total_claims=len(crs)), claim_results=crs))
        await decide_verdict(ms)
        s = ms.verifications.summary
        g = r["gold"]
        match = (s.verdict_counts == g["verdict_counts"]
                 and abs(s.overall_confidence - g["overall_confidence"]) < 1e-6
                 and abs(s.coverage - g["coverage"]) < 1e-6)
        n += 1
        ok += match
    return f"시나리오 {ok}/{n} 정확 (counts·confidence·coverage 모두 일치)"


def test9():
    return asyncio.run(_run9())


# ── [10] generate_explanation 템플릿 (결정적, 오프라인) ──
def test10():
    rows = [r for r in jl(f"{PFX}generate_explanation.jsonl") if r.get("scorable")]
    n = ran = empty = 0
    for r in rows:
        cr = ClaimResult(
            claim_id="c", verdict=r["claim_result"]["verdict"],
            claim_value=r["claim_result"]["claim_value"] or "",
            kosis_value=r["claim_result"]["kosis_value"],
            mismatch_type=r["claim_result"]["mismatch_type"],
            evidence=[Evidence(claim_id="c", source="KOSIS", subject="x", unit="",
                               period_type="Y", period="", population="x",
                               table_name=(r["claim_result"]["evidence"][0]["table_name"]
                                           if r["claim_result"]["evidence"] else None))],
        )
        clm = _claim({"claim_type": "absolute", "value_llm": "", "unit": r["claim"].get("unit"),
                      "period_llm": r["claim"].get("period_llm")})
        clm.subject = r["claim"].get("subject") or "x"
        clm.period_type = r["claim"].get("period_type") or "Y"
        s = _build_explanation(cr, clm)
        n += 1
        ran += bool(s)
        empty += (not s)
    return f"템플릿 렌더 {ran}/{n} 성공(빈문자열 {empty}) — 결정적 실행 확인"


# ── [3] normalize 룰 베이스 (오프라인; LLM 폴백 제외) ──
async def _run3():
    rows = jl(f"{PFX}normalize_claim.jsonl")
    nv = okv = 0
    for r in rows:
        raw = r["value"]["raw"]
        exp = r["gold"]["value"]["expected"]
        got = await _parse_value(raw)  # 룰만(실패 시 None)
        nv += 1
        okv += (got == exp)
    return f"value 룰 베이스 정확도 {okv}/{nv} = {okv/nv:.0%} (LLM 폴백 제외 — 룰 커버리지 하한)"


def test3():
    return asyncio.run(_run3())


if __name__ == "__main__":
    print("[3 normalize 룰]", test3())
    print("[7 calculate_metric]", test7())
    print("[9 decide_verdict]", test9())
    print("[10 explanation 템플릿]", test10())
