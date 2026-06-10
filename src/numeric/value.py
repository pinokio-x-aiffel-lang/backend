"""주장 수치(value.llm_value) 파싱 — numeric layer 입력 정규화. [파이프라인 7]

normalize_claim([3]) 이 만든 표준 문자열을 비교 가능한 형태로 해석한다.
형식: 평문(38.8) / 부호(+3.0,-5.0) / 범위(50~100,>=5) / 비(3:2) / 단독부호(+,-) / 파싱불가.
ABSOLUTE 직접비교는 kind==SCALAR 만 쓴다(부호·범위·비는 그룹/추가 처리 영역).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class ValueKind(str, Enum):
    SCALAR = "scalar"        # 단일 절대 수치 (38.8)
    SIGNED = "signed"        # 부호 있는 변화량 (+3.0, -5.0)
    RANGE = "range"          # 범위/부등 (50~100, >=5, <10)
    RATIO = "ratio"          # 비 (3:2)
    BARE_SIGN = "bare_sign"  # 방향만 (+, -)
    UNPARSABLE = "unparsable"


@dataclass(frozen=True)
class ParsedValue:
    """파싱 결과. number 는 SCALAR/SIGNED 일 때만 채워진다(그 외 None)."""

    kind: ValueKind
    number: float | None
    raw: str


_NUM = re.compile(r"[+-]?\d[\d,]*(?:\.\d+)?")


def parse_claim_value(llm_value: str) -> ParsedValue:
    """value.llm_value → ParsedValue. 분기 순서가 곧 우선순위."""
    s = (llm_value or "").strip()
    if not s:
        return ParsedValue(ValueKind.UNPARSABLE, None, llm_value or "")
    if s in ("+", "-"):
        return ParsedValue(ValueKind.BARE_SIGN, None, s)
    # 범위/부등 (음수 -5.0 와 구분: 부등호/물결 기준)
    if "~" in s or s[:2] in (">=", "<=") or s[:1] in ("<", ">"):
        return ParsedValue(ValueKind.RANGE, None, s)
    if ":" in s:
        return ParsedValue(ValueKind.RATIO, None, s)
    if _NUM.fullmatch(s):
        kind = ValueKind.SIGNED if s[0] in "+-" else ValueKind.SCALAR
        return ParsedValue(kind, float(s.replace(",", "")), s)
    return ParsedValue(ValueKind.UNPARSABLE, None, s)
