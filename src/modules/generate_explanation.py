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
_VERDICT_LABEL = {"T": "일치", "F": "불일치", "M": "검토 필요", "N": "검증 불가"}


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
    """종합 의견 LLM 입력용 주장 1건 요약 한 줄."""
    subject = claim.subject if claim else "해당 지표"
    unit = (claim.unit if claim else "") or ""
    period_str = (
        _format_period(claim.period_type, claim.period_value.llm_value).strip()
        if claim else ""
    )
    label = _VERDICT_LABEL.get(result.verdict, "검증 불가")
    kosis = f"{result.kosis_value}{unit}" if result.kosis_value is not None else "없음"
    mismatch = f", 불일치 유형 {result.mismatch_type}" if result.mismatch_type else ""
    head = f"{period_str} {subject}".strip()
    return f"- {head}: 기사 {result.claim_value}{unit} / KOSIS {kosis} → {label}{mismatch}"


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


def _dominant_label(counts: dict[str, int]) -> str:
    """분포에서 가장 심각한 verdict 의 한국어 라벨(F>M>N>T). 옛 overall_verdict 라벨 대체."""
    for code in ("F", "M", "N", "T"):
        if counts.get(code):
            return _VERDICT_LABEL.get(code, "검증 불가")
    return "검증 불가"


async def _generate_opinion(
    results: list[ClaimResult], claim_map: dict[str, Claim],
    counts: dict[str, int],
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
                overall=_dominant_label(counts),
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
    summary = master_schema.verifications.summary
    counts = _count_verdicts(results)
    if not results:
        summary.overall_opinion = _fallback_opinion(counts, 0)
        return
    opinion = await _generate_opinion(results, claim_map, counts)
    summary.overall_opinion = opinion or _fallback_opinion(counts, len(results))
