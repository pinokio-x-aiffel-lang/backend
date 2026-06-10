from __future__ import annotations

import json

from src.llm.client import LlmError
from src.llm.model_presets import RANK_EVIDENCE
from src.observability.tracing import traced_chat
from src.prompts.prompts import RANK_EVIDENCE_SYSTEM, RANK_EVIDENCE_USER
from src.schemas.runtime import Claim, Evidence, MasterSchema

# LLM 응답 구조(structured outputs): 보기 index 또는 null(적합 표 없음).
_RANK_SCHEMA = {
    "type": "object",
    "properties": {"chosen_index": {"type": ["integer", "null"]}},
    "required": ["chosen_index"],
}


class RankEvidenceError(Exception):
    """증거 랭킹 실패."""


async def rank_evidence(master_schema: MasterSchema) -> None:
    """
    [6] Rank Evidence — 후보 표 중 주장에 '가장 적합한 표'를 LLM 으로 1위 선정.

    Input:  master_schema.analysis[*].evidences  ([5]가 내보낸 매칭 표 n개, RANK 순)
    Output: 각 analysis.evidences 를 재정렬해 1위(적합 표)를 evidences[0] 으로.

    값은 보지 않고 표의 주제 적합도(표명·분류축)만으로 고른다 — 값 근접으로 표를 고르면
    확증 편향이 생기기 때문. [7] calculate_metric 이 evidences[0](=1위)부터 비교한다.
    후보가 0/1개면 LLM 생략. LLM 실패/기권은 기존 RANK 순 유지(raise 안 함).
    """
    claims = {c.claim_id: c for c in master_schema.claims}
    for analysis in master_schema.analysis:
        evs = analysis.evidences
        if len(evs) < 2:                       # 고를 게 없음 → 그대로
            continue
        claim = claims.get(analysis.claim_id)
        if claim is None:
            continue
        idx = _rank_top(claim, evs, analysis.cell_attempts)
        if idx is not None and 0 <= idx < len(evs) and idx != 0:
            analysis.evidences = [evs[idx], *evs[:idx], *evs[idx + 1:]]  # 1위를 맨 앞으로


def _axis_label(tbl_id: str, cell_attempts) -> str:
    """그 표의 분류축 종류(예: '국가별, 성별')를 cell_attempts 에서 가져온다(표시용)."""
    for a in cell_attempts:
        if a.tbl_id == tbl_id and a.axes:
            return ", ".join(a.axes.keys())
    return ""


def _rank_top(claim: Claim, evidences: list[Evidence], cell_attempts) -> int | None:
    """주제 적합도로 1위 표 index 를 LLM 에게 고르게 한다. 실패/기권 시 None."""
    options = "\n".join(
        f"  [{i}] {ev.table_name or ev.kosis_tbl_id}"
        + (f" | 분류축: {ax}" if (ax := _axis_label(ev.kosis_tbl_id, cell_attempts)) else "")
        for i, ev in enumerate(evidences)
    )
    messages = [
        {"role": "system", "content": RANK_EVIDENCE_SYSTEM},
        {"role": "user", "content": RANK_EVIDENCE_USER.format(
            subject=claim.subject, population=claim.population,
            unit=claim.unit, period=f"{claim.period_type}:{claim.period_value.llm_value}",
            options=options,
        )},
    ]
    try:
        resp = traced_chat(
            model_alias=RANK_EVIDENCE.model_alias, model_name=RANK_EVIDENCE.model_name,
            messages=messages, max_tokens=RANK_EVIDENCE.max_tokens,
            temperature=RANK_EVIDENCE.temperature, json_structure=_RANK_SCHEMA,
            trace_name="rank_evidence:select",
        )
        data = json.loads(resp.text.strip())
    except (LlmError, AttributeError, json.JSONDecodeError):
        return None
    idx = data.get("chosen_index")
    return int(idx) if isinstance(idx, int) else None
