from __future__ import annotations

import asyncio
import re

from src.llm.client import LlmError
from src.llm.model_presets import GENERATE_OPINION
from src.observability.tracing import traced_chat
from src.prompts.prompts import GENERATE_OPINION_SYSTEM, GENERATE_OPINION_USER
from src.schemas.runtime import Claim, ClaimResult, MasterSchema


class GenerateExplanationError(Exception):
    """설명 생성 실패."""


# verdict 코드 → 사람용 라벨. 종합 의견 입력·폴백 총평 공용.
_VERDICT_LABEL = {"T": "일치", "F": "불일치", "M": "검토필요", "N": "검증불가"}

# mismatch_type(영문 코드) → 한국어 사유. 종합 의견 입력에서 jargon 노출 방지.
_MISMATCH_LABEL = {
    "magnitude": "값 크기 차이",
    "rounding": "반올림 경계",
    "direction": "증감 방향 차이",
    "unit": "단위 불일치",
    "period": "기간 불일치",
    "population": "모집단 차이",
    "subject": "측정 주제 차이",
    "aggregation": "집계 방식 차이",
}


def _has_batchim(text: str) -> bool:
    """텍스트의 마지막 한글 음절에 받침이 있으면 True."""
    for ch in reversed(text):
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            return (code - 0xAC00) % 28 != 0
    return False


def _eun_neun(text: str) -> str:
    return "은" if _has_batchim(text) else "는"


def _format_period(period_type: str, period: str) -> str:
    """기간 코드 → 한국어 기간 문자열. 정규화 형식(YYYY-MM 등)과 KOSIS PRD_DE 형식(YYYYMM 등) 모두 처리."""
    p = period.strip()
    if period_type == "Y":
        y = p[:4] if len(p) >= 4 and p[:4].isdigit() else p
        return f"{y}년 "
    if period_type == "M":
        m = re.match(r"(\d{4})-(\d{2})", p)
        if m:
            return f"{m.group(1)}년 {int(m.group(2))}월 "
        if len(p) == 6 and p.isdigit():
            return f"{p[:4]}년 {int(p[4:])}월 "
    if period_type == "Q":
        m = re.match(r"(\d{4})-Q([1-4])", p)
        if m:
            return f"{m.group(1)}년 {m.group(2)}분기 "
        if len(p) == 6 and p.isdigit():
            return f"{p[:4]}년 {int(p[4:])}분기 "
    if period_type == "S":
        m = re.match(r"(\d{4})-H([12])", p)
        if m:
            half = "상" if m.group(2) == "1" else "하"
            return f"{m.group(1)}년 {half}반기 "
        if len(p) == 6 and p.isdigit():
            half = "상" if int(p[4:]) == 1 else "하"
            return f"{p[:4]}년 {half}반기 "
    if period_type == "D":
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", p)
        if m:
            return f"{m.group(1)}년 {int(m.group(2))}월 {int(m.group(3))}일 "
        if len(p) == 8 and p.isdigit():
            return f"{p[:4]}년 {int(p[4:6])}월 {int(p[6:])}일 "
    return ""


def _build_explanation(result: ClaimResult, claim: Claim | None) -> str:
    subject = claim.subject if claim else "해당 지표"
    unit = (claim.unit if claim else "") or ""
    period_str = (
        _format_period(claim.period_type, claim.period_value.llm_value) if claim else ""
    )

    ev = result.evidence[0] if result.evidence else None
    source_note = f" (출처: {ev.table_name})" if ev and ev.table_name else ""

    claim_display = f"{result.claim_value}{unit}"
    kosis_display = f"{result.kosis_value}{unit}" if result.kosis_value is not None else ""

    v = result.verdict

    if v == "T":
        return (
            f"기사의 {period_str}{subject} {claim_display}{_eun_neun(claim_display)}"
            f" KOSIS 공식 수치와 일치합니다.{source_note}"
        )
    if v == "F":
        mismatch = f" 불일치 유형: {result.mismatch_type}." if result.mismatch_type else ""
        return (
            f"기사의 {period_str}{subject} {claim_display}{_eun_neun(claim_display)}"
            f" KOSIS 공식 수치({kosis_display})와 다릅니다.{mismatch}{source_note}"
        )
    if v == "M":
        return (
            f"기사의 {period_str}{subject} {claim_display}{_eun_neun(claim_display)}"
            f" KOSIS 공식 수치({kosis_display})와 부분적으로 일치합니다.{source_note}"
        )
    # NEI, UNVERIFIED, 기타 — 검증 불가
    return f"{period_str}{subject}에 대한 KOSIS 공식 통계를 찾지 못해 검증할 수 없습니다."


# ── 기사 단위 종합 의견 ────────────────────────────────────────────────────────

def _count_verdicts(results: list[ClaimResult]) -> dict[str, int]:
    """claim별 verdict 분포. T/F/M/N 외 값은 N(검증 불가)으로 집계."""
    counts = {"T": 0, "F": 0, "M": 0, "N": 0}
    for r in results:
        counts[r.verdict if r.verdict in counts else "N"] += 1
    return counts


def _claim_line(result: ClaimResult, claim: Claim | None) -> str:
    """종합 의견 LLM 입력용 주장 1건 요약 한 줄. verdict 라벨을 맨 앞에 두고,
    수치 일치 여부를 =/≠ 로 못 박는다. 특히 검토필요(M)는 '수치는 일치하나
    해석 오도'임을 명시해 불일치(F=수치 자체가 틀림)와 섞이지 않게 한다.
    예: '[검토필요] 2024년 주당 평균 근로시간: 기사 38.8시간 = 공식 38.8시간
        (수치는 일치하나 모집단 차이로 표현 오도)'"""
    subject = claim.subject if claim else "해당 지표"
    unit = (claim.unit if claim else "") or ""
    period_str = (
        _format_period(claim.period_type, claim.period_value.llm_value).strip()
        if claim else ""
    )
    label = _VERDICT_LABEL.get(result.verdict, "검증불가")
    head = f"{period_str} {subject}".strip()
    cv = f"{result.claim_value}{unit}"
    kv = f"{result.kosis_value}{unit}" if result.kosis_value is not None else None
    reason = _MISMATCH_LABEL.get(result.mismatch_type or "", "")

    if result.verdict == "T":
        body = f"기사 {cv} = 공식 {kv} (수치 일치)"
    elif result.verdict == "F":
        why = f"수치 불일치, {reason}" if reason else "수치 불일치"
        body = f"기사 {cv} ≠ 공식 {kv} ({why})"
    elif result.verdict == "M":
        why = f"수치는 일치하나 {reason}로 표현 오도" if reason else "수치는 일치하나 표현 오도"
        body = f"기사 {cv} = 공식 {kv} ({why})"
    else:  # N — 검증 불가
        body = f"기사 {cv}, 공식 통계 없음 (검증 불가)"
    return f"[{label}] {head}: {body}"


def _fallback_opinion(counts: dict[str, int], total: int) -> str:
    """LLM 실패·미사용 시 결정적 템플릿 총평. 분포 + verdict 기반 한 문장."""
    if total == 0:
        return "검증할 통계 주장을 찾지 못했습니다."
    dist = (
        f"총 {total}개 주장 중 일치 {counts['T']}건, 불일치 {counts['F']}건, "
        f"검토 필요 {counts['M']}건, 검증 불가 {counts['N']}건으로 확인되었습니다."
    )
    if counts["F"] > 0:
        tail = " 일부 통계 인용에서 공식 수치와 다른 값이 확인되어 주의가 필요합니다."
    elif counts["M"] > 0:
        tail = " 수치는 대체로 맞으나 일부 표현에서 해석상 검토가 필요합니다."
    elif counts["T"] == total:
        tail = " 검증된 통계 인용은 모두 공식 수치와 일치합니다."
    else:
        tail = " 검증 가능한 공식 통계를 충분히 확보하지 못했습니다."
    return dist + tail


async def _generate_opinion(
    results: list[ClaimResult], claim_map: dict[str, Claim],
    counts: dict[str, int], confidence: float,
) -> str | None:
    """claim별 결과 요약을 근거로 기사 단위 종합 의견을 LLM 생성. 실패 시 None."""
    claim_lines = "\n".join(_claim_line(r, claim_map.get(r.claim_id)) for r in results)
    messages = [
        {"role": "system", "content": GENERATE_OPINION_SYSTEM},
        {
            "role": "user",
            "content": GENERATE_OPINION_USER.format(
                total=len(results),
                n_true=counts["T"], n_false=counts["F"],
                n_review=counts["M"], n_nei=counts["N"],
                confidence=f"{round(confidence * 100)}%",
                claim_lines=claim_lines,
            ),
        },
    ]
    try:
        resp = await asyncio.to_thread(
            traced_chat,
            model_alias=GENERATE_OPINION.model_alias,
            model_name=GENERATE_OPINION.model_name,
            messages=messages,
            max_tokens=GENERATE_OPINION.max_tokens,
            temperature=GENERATE_OPINION.temperature,
            trace_name="generate_explanation:opinion",
        )
        return resp.text.strip() or None
    except (LlmError, AttributeError, ValueError):
        return None


async def generate_explanation(master_schema: MasterSchema) -> None:
    """
    [10] Generate Explanation

    Input:
        master_schema.verifications   # [9]에서 조립된 판정 결과
        master_schema.claims          # subject, unit, period 참조

    Output:
        master_schema.verifications.claim_results[*].explanation   # claim별 템플릿 설명
        master_schema.verifications.summary.overall_opinion        # 기사 단위 LLM 종합 의견

    Responsibility:
        1) claim별: verdict·수치 차이를 근거로 한국어 템플릿 설명을 생성(결정적).
        2) 기사별: claim 결과 요약을 LLM 에 주고 종합 의견 한 문단을 생성한다.
           LLM 실패 시 결정적 템플릿 총평으로 폴백(전체 run 은 중단하지 않는다).
    """
    if master_schema.verifications is None:
        return

    claim_map: dict[str, Claim] = {c.claim_id: c for c in master_schema.claims}
    results = master_schema.verifications.claim_results

    # 1) claim별 템플릿 설명
    for result in results:
        result.explanation = _build_explanation(result, claim_map.get(result.claim_id))

    # 2) 기사 단위 종합 의견 (LLM, 실패 시 결정적 폴백)
    #    분포는 [9] decide_verdict 가 확정한 verdict_counts 를 우선 사용([9] 미실행 시 폴백).
    summary = master_schema.verifications.summary
    counts = summary.verdict_counts or _count_verdicts(results)
    if not results:
        summary.overall_opinion = _fallback_opinion(counts, 0)
        return
    opinion = await _generate_opinion(results, claim_map, counts, summary.overall_confidence)
    summary.overall_opinion = opinion or _fallback_opinion(counts, len(results))
