"""[10] generate_explanation 평가 (제대로) — ① 템플릿 실측 회귀 ② opinion 루브릭(LLM 심판).

① 템플릿: 모듈을 실제 실행해 claim 설명 vs gold_template 비교(하드코딩 제거). 결정적이라
   ~1.0 기대지만 '실측'이며 템플릿 회귀를 잡는다.
② opinion: overall_opinion(LLM 자유문장)을 LLM 심판이 루브릭 3기준(분포반영·모순없음·환각없음)
   O/X 채점 → 기준별 통과율. (LLM-as-judge)

입력=260619 캡처 after9(판정 결과, 고정), gold=10_source_2 gold_template + opinion_rubric.
실행: uv run x python benchmark/eval_stage10.py
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from benchmark.reporting import save_result, blank_sections
from benchmark.scoring import score_explanation, prop_row, value_row
from src.llm.llm_caller import LlmCaller
from src.llm.client import LlmError
from src.llm.model_presets import GENERATE_OPINION
from src.modules.generate_explanation import generate_explanation
from src.schemas.runtime import MasterSchema

ROOT = Path(__file__).resolve().parent.parent
CAP = ROOT / "benchmark_aain/data/260619_capture_v2_snapshots.jsonl"
GOLD = ROOT / "benchmark/data/10_explanation/10_source_2.jsonl"

JUDGE_SYS = (
    "당신은 사실검증 시스템의 '기사 종합 의견'을 채점하는 평가자다. "
    "주어진 판정 분포와 종합 의견을 보고 3개 기준 각각 통과(true)/실패(false)를 판정한다. "
    "기준: (1) distribution_reflected=의견이 판정 분포(T/F/M/N 개수·비율)를 정확히 반영했나, "
    "(2) no_contradiction=판정 결과와 모순된 단정을 하지 않았나, "
    "(3) no_hallucination=근거에 없는 수치/사실을 지어내지 않았나. "
    "반드시 아래 JSON 형식으로만 답한다(설명 금지): "
    '{"distribution_reflected": true/false, "no_contradiction": true/false, "no_hallucination": true/false}'
)


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def judge_opinion(caller, opinion, counts):
    user = (f"판정 분포: T={counts.get('T',0)} F={counts.get('F',0)} "
            f"M={counts.get('M',0)} N={counts.get('N',0)}\n종합 의견: \"{opinion}\"")
    try:
        resp = caller.chat(
            model_alias=GENERATE_OPINION.model_alias, model_name=GENERATE_OPINION.model_name,
            messages=[{"role": "system", "content": JUDGE_SYS}, {"role": "user", "content": user}],
            temperature=0.0, max_tokens=GENERATE_OPINION.max_tokens,
        )
        m = re.search(r"\{.*\}", resp.text, re.DOTALL)
        d = json.loads(m.group(0)) if m else {}
        return {k: bool(d.get(k)) for k in ("distribution_reflected", "no_contradiction", "no_hallucination")}
    except (LlmError, ValueError, AttributeError, json.JSONDecodeError):
        return None


async def main():
    import sys
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    cap = load(CAP)
    if limit:
        cap = cap[:limit]
    gold_tpl = {}  # (row_id, claim_id) → gold_template
    for g in load(GOLD):
        gold_tpl[(g["row_id"], g["claim_id"])] = g.get("gold_template")
    caller = LlmCaller()

    tmpl_records = []   # 단계10 채점(per claim): template_match
    rubric = []         # per article: 3 기준 bool
    sem = asyncio.Semaphore(5)

    async def one(row):
        async with sem:
            snap = (row.get("snapshots") or {}).get("after9")
            if not snap:
                return
            ms = MasterSchema.model_validate(snap)
            await generate_explanation(ms)  # 실제 실행(claim 템플릿 + LLM opinion)
            v = ms.verifications
            # ① 템플릿 실측
            for cr in v.claim_results:
                g = gold_tpl.get((row["row_id"], cr.claim_id))
                if g is None:
                    continue
                tmpl_records.append({
                    "row_id": row["row_id"], "stage": 10,
                    "input": {"verifications": {"claim_results": [{"claim_id": cr.claim_id}]},
                              "claims": [{"claim_id": cr.claim_id}]},
                    "output": {"explanation": cr.explanation},
                    "gold_template": g, "template_match": cr.explanation == g,
                })
            # ② opinion 루브릭
            op = (v.summary.overall_opinion or "").strip()
            counts = dict(v.summary.verdict_counts)
            verdict = judge_opinion(caller, op, counts) if op else None
            rubric.append({"row_id": row["row_id"], "opinion": op[:120],
                           "judged": verdict is not None, **(verdict or {})})

    await asyncio.gather(*[one(r) for r in cap if not r.get("failed_step")])

    # 지표: 템플릿 실측 + opinion 루브릭 기준별 통과율
    metrics = score_explanation(tmpl_records)
    judged = [r for r in rubric if r.get("judged")]
    for key, label in [("distribution_reflected", "opinion: 분포 반영"),
                       ("no_contradiction", "opinion: verdict 모순 없음"),
                       ("no_hallucination", "opinion: 환각 없음")]:
        metrics.append(prop_row(label, "rubric", sum(1 for r in judged if r.get(key)), len(judged)))
    metrics.append(value_row("opinion 생성/채점 수", "count", f"{len(judged)}/{len(rubric)}"))

    sec = blank_sections()
    sec["개요"] = "10단계 generate_explanation — ① claim 템플릿 실측 회귀 ② overall_opinion LLM-심판 루브릭(분포반영·모순없음·환각없음)."
    sec["테스트 방법"] = ("입력=260619 캡처 after9(판정 고정)→generate_explanation 실제 실행. "
                     "① 템플릿: 모듈 claim 설명 vs gold_template(=_build_explanation 스냅샷) 실비교. "
                     "② opinion: overall_opinion 을 심판 LLM(GENERATE_OPINION preset)이 3기준 O/X.")
    sec["분석"] = ("템플릿은 결정적이라 ~1.0(회귀 정상). 의미 있는 품질은 opinion 루브릭 통과율. "
                 "하드코딩 True 제거 — 이제 실측.")
    sec["한계·주의"] = ("LLM-심판은 1회·temperature=0(변동 최소화)이나 사람 검증 아님. "
                    "opinion 은 cascade 판정(거의 N) 기반이라 분포반영이 'N 다수'를 반영했나로 치우칠 수 있음.")
    j, d = save_result(10, "leeaain", tmpl_records, metrics, sec)
    print(f"[stage 10] 템플릿 records={len(tmpl_records)} | opinion judged={len(judged)}/{len(rubric)} → {j.name}")
    for m in metrics:
        print(f"   {m['지표']} {m['값']} {m.get('95% CI','')}")


if __name__ == "__main__":
    asyncio.run(main())
