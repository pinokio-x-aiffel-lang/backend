"""[8] Check Alignment — 7단계가 T(수치 일치)로 본 건의 '해석'을 재판정한다.

수치가 맞다(T)는 건 '숫자'가 같다는 뜻일 뿐, 기사가 그 숫자를 올바로 해석했는지는
별개다. 기사 주장이 KOSIS 수치가 나타내는 바를 오도/강하게 왜곡 없이 전달했으면 T 유지,
오도/왜곡이면 M, LLM 판정 실패면 NEI(근거 기록). F/NEI 는 손대지 않고 통과한다
(F=수치 자체를 잘못 인용=확정 가짜, NEI=판단 불가).
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from src.llm.client import LlmError
from src.llm.model_presets import CHECK_ALIGNMENT
from src.observability.tracing import traced_chat
from src.prompts.prompts import CHECK_ALIGNMENT_SYSTEM, CHECK_ALIGNMENT_USER
from src.schemas.runtime import (
    Claim,
    Evidence,
    MasterSchema,
    MetricResult,
    MismatchType,
    Verdict,
)


class CheckAlignmentError(Exception):
    """정합성 판단 실패."""


# LLM 정합성 판정 응답 구조(structured outputs).
_ALIGNMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "aligned": {"type": "boolean"},
        "dimension": {"type": ["string", "null"]},
        "reason": {"type": "string"},
    },
    "required": ["aligned", "dimension", "reason"],
}

# LLM 이 짚은 오도/왜곡 차원 → mismatch_type 매핑.
_DIMENSION_TO_MISMATCH = {
    "subject": MismatchType.SUBJECT,
    "population": MismatchType.POPULATION,
    "unit": MismatchType.UNIT,
    "aggregation": MismatchType.AGGREGATION,
    "period": MismatchType.PERIOD,
}


@dataclass(frozen=True)
class AlignmentJudgment:
    """LLM 정합성 판정 결과."""

    aligned: bool
    dimension: str | None
    reason: str


async def check_alignment(master_schema: MasterSchema) -> None:
    """
    [8] Check Alignment

    Input(read):
        verifications.claim_results[*].metric  # verdict==T 만 대상
        claims[*], analysis[*].evidence        # 기사 주장 ↔ KOSIS 수치 의미
    Output(write):
        claim_results[*].metric 의 verdict(T→T/M/NEI)·mismatch_type·align_reason·align_source

    수치 일치(T)건만 LLM 으로 '기사가 수치를 오도/왜곡 없이 전달했나' 재판정한다.
    F/NEI 는 통과. 실패 시 raise → runner(개별 LLM 실패는 NEI 로 강등, raise 아님).
    """
    if master_schema.verifications is None:
        return

    claims = {c.claim_id: c for c in master_schema.claims}
    # [6]이 정렬한 1위 적합 표(evidences[0])로 정합성 판정 — [7]이 비교한 표와 동일하게.
    evidence_by_claim = {
        a.claim_id: (a.evidences[0] if a.evidences else None)
        for a in master_schema.analysis
    }

    targets = [
        cr
        for cr in master_schema.verifications.claim_results
        if cr.metric is not None
        and cr.metric.verdict == Verdict.TRUE
        and claims.get(cr.claim_id) is not None
        and evidence_by_claim.get(cr.claim_id) is not None
    ]
    if not targets:
        return

    judgments = await asyncio.gather(
        *(
            _judge(claims[cr.claim_id], evidence_by_claim[cr.claim_id])
            for cr in targets
        )
    )

    for cr, judgment in zip(targets, judgments):
        apply_alignment(cr.metric, judgment)
        # 상위 표시 필드 미러링(generate_explanation 등 하위호환).
        cr.verdict = cr.metric.verdict.value if cr.metric.verdict else cr.verdict
        cr.mismatch_type = (
            cr.metric.mismatch_type.value if cr.metric.mismatch_type else cr.mismatch_type
        )


def apply_alignment(metric: MetricResult, judgment: AlignmentJudgment | None) -> None:
    """정합성 판정으로 metric 을 제자리 보정. 대상은 verdict==T 인 metric.

    - 일치(aligned)       → T 유지
    - 오도/왜곡(not aligned) → M (+ 어긋난 차원)
    - LLM 실패(judgment None) → NEI (+ 근거)
    """
    if judgment is None:
        metric.verdict = Verdict.NOT_ENOUGH_INFO
        metric.align_source = "llm_failed"
        metric.align_reason = "정합성 LLM 판정 실패"
        return

    metric.align_source = "llm"
    metric.align_reason = judgment.reason

    if judgment.aligned:
        metric.verdict = Verdict.TRUE
        metric.mismatch_type = None
    else:
        metric.verdict = Verdict.NEEDS_REVIEW
        mt = _DIMENSION_TO_MISMATCH.get((judgment.dimension or "").strip().lower())
        if mt is not None:
            metric.mismatch_type = mt


async def _judge(claim: Claim, evidence: Evidence) -> AlignmentJudgment | None:
    """기사 주장이 수치를 오도/왜곡 없이 전달했나 LLM 판정. 실패 시 None."""
    messages = [
        {"role": "system", "content": CHECK_ALIGNMENT_SYSTEM},
        {
            "role": "user",
            "content": CHECK_ALIGNMENT_USER.format(
                sentence=claim.sentence,
                claim_subject=claim.subject,
                claim_population=claim.population or "(불명)",
                claim_unit=claim.unit or "(없음)",
                claim_aggregation=claim.aggregation or "(불명)",
                claim_period=claim.period_value.llm_value,
                ev_table_name=evidence.table_name or "(불명)",
                ev_subject=evidence.subject,
                ev_population=evidence.population or "(불명)",
                ev_unit=evidence.unit or "(없음)",
                ev_period=evidence.period,
                ev_population_fallback="예" if evidence.population_fallback else "아니오",
            ),
        },
    ]
    try:
        resp = await asyncio.to_thread(
            traced_chat,
            model_alias=CHECK_ALIGNMENT.model_alias,
            model_name=CHECK_ALIGNMENT.model_name,
            messages=messages,
            max_tokens=CHECK_ALIGNMENT.max_tokens,
            temperature=CHECK_ALIGNMENT.temperature,
            json_structure=_ALIGNMENT_SCHEMA,
            trace_name="check_alignment:judge",
        )
        data = json.loads(resp.text.strip())
        return AlignmentJudgment(
            aligned=bool(data["aligned"]),
            dimension=data.get("dimension"),
            reason=str(data.get("reason", "")),
        )
    except (LlmError, AttributeError, KeyError, ValueError, json.JSONDecodeError):
        return None
