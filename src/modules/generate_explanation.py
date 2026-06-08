from __future__ import annotations

import re

from src.schemas.runtime import Claim, ClaimResult, MasterSchema


class GenerateExplanationError(Exception):
    """설명 생성 실패."""


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


async def generate_explanation(master_schema: MasterSchema) -> None:
    """
    [10] Generate Explanation

    Input:
        master_schema.verifications   # [9]에서 조립된 판정 결과
        master_schema.claims          # subject, unit, period 참조

    Output:
        master_schema.verifications.claim_results[*].explanation

    Responsibility:
        verdict·수치 차이를 근거로 한국어 템플릿 설명을 생성해
        각 claim_result 의 explanation 을 채운다.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    if master_schema.verifications is None:
        return

    claim_map: dict[str, Claim] = {c.claim_id: c for c in master_schema.claims}

    for result in master_schema.verifications.claim_results:
        claim = claim_map.get(result.claim_id)
        result.explanation = _build_explanation(result, claim)
