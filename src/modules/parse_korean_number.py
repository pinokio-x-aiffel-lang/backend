"""한국어 수사 파서 — 한자어·고유어 수사 및 큰 수 단위 → 숫자 문자열 (룰 전용·동기).

공개 룰 함수:
    _parse_number_rule(raw)          아라비아+큰수단위(만/억/조/경) → 숫자 문자열
    _parse_korean_numeral_rule(raw)  한자어·고유어 수사            → 숫자 문자열

LLM 폴백은 호출부(normalize_claim._resolve_value)가 룰 전부 실패 시 한 번만 담당한다.
"""
from __future__ import annotations

import re

# ── 상수 ──────────────────────────────────────────────────────────────────────

_BIG = [("경", 10**16), ("조", 10**12), ("억", 10**8), ("만", 10**4)]
_SMALL = {"천": 1_000, "백": 100, "십": 10}
_UNIT_CHARS = "만억조경천백십"
_SINO_DIGIT = "일이삼사오육칠팔구"

_SINO = {
    "일": 1, "이": 2, "삼": 3, "사": 4, "오": 5,
    "육": 6, "칠": 7, "팔": 8, "구": 9,
    "십": 10, "백": 100, "천": 1_000,
}
_NATIVE = {
    "하나": 1, "둘": 2, "셋": 3, "넷": 4, "다섯": 5,
    "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9,
    "열": 10, "스물": 20, "서른": 30, "마흔": 40, "쉰": 50,
    "예순": 60, "일흔": 70, "여든": 80, "아흔": 90,
    "한": 1, "두": 2, "세": 3, "네": 4, "스무": 20,
}


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _coeff(s: str) -> float:
    s = s.strip()
    if not s:
        return 1.0
    try:
        return float(s)
    except ValueError:
        val = 0.0
        for m in re.finditer(r"(\d*(?:\.\d+)?)\s*([천백십])", s):
            val += float(m.group(1) or "1") * _SMALL[m.group(2)]
        return val or 1.0


def _parse_sino(s: str) -> int | None:
    """한자어 수사 → 정수. "삼십이" → 32."""
    s = s.strip()
    m = re.fullmatch(r"제(\d+)", s)
    if m:
        return int(m.group(1))
    result, current = 0, 0
    i = 0
    while i < len(s):
        matched = False
        for word in ("천", "백", "십"):
            if s[i:].startswith(word):
                result += (current or 1) * _SINO[word]
                current = 0
                i += len(word)
                matched = True
                break
        if not matched:
            for word in ("일", "이", "삼", "사", "오", "육", "칠", "팔", "구"):
                if s[i:].startswith(word):
                    current = _SINO[word]
                    i += len(word)
                    matched = True
                    break
        if not matched:
            return None
    result += current
    return result if result > 0 else None


def _parse_sino_with_units(s: str) -> int | None:
    """한자어 수사 + 큰 수 단위. "백이십만"→1200000, "오천억"→500000000000.

    단위(만/억/조/경)로 끊어 각 구간을 _parse_sino 로 계수화한다.
    큰 수 단위가 없으면 _parse_sino 와 동일하게 동작한다.
    """
    s = s.strip()
    total = 0
    rest = s
    for unit_char, unit_val in _BIG:          # 경·조·억·만 순
        if unit_char in rest:
            pre, rest = rest.split(unit_char, 1)
            if pre:
                coeff = _parse_sino(pre)
                if coeff is None:
                    return None
            else:
                coeff = 1                      # "만"·"억" 단독 = 단위값
            total += coeff * unit_val
    if rest:                                   # 단위 뒤 잔여(천/백/십/일~구)
        tail = _parse_sino(rest)
        if tail is None:
            return None
        total += tail
    return total if total > 0 else None


def _parse_native(s: str) -> int | None:
    """고유어 수사 → 정수. "스물셋" → 23."""
    s = s.strip()
    ordinals = {"첫째": 1, "둘째": 2, "셋째": 3, "넷째": 4, "다섯째": 5}
    if s in ordinals:
        return ordinals[s]
    tens_words = ["아흔", "여든", "일흔", "예순", "쉰", "마흔", "서른", "스무", "스물", "열"]
    units_words = ["아홉", "여덟", "일곱", "여섯", "다섯", "넷", "셋", "둘", "하나",
                   "네", "세", "두", "한"]
    tens, ones, rest = 0, 0, s
    for w in tens_words:
        if rest.startswith(w):
            tens = _NATIVE[w]
            rest = rest[len(w):]
            break
    for w in units_words:
        if rest == w:
            ones = _NATIVE[w]
            rest = ""
            break
    if rest:
        return None
    total = tens + ones
    return total if total > 0 else None


# ── 규칙 베이스 (private) ──────────────────────────────────────────────────────

def _parse_number_rule(raw: str) -> str | None:
    """아라비아+큰수단위(만/억/조/경) 규칙 파싱. 실패 시 None."""
    s = raw.strip().replace(",", "")
    # 한자어 숫자 글자가 단위 글자 바로 앞에 오면 처리 불가 → LLM에게
    # 예: "오천억"(오+천), "이십만"(이+십) — 일반 단어의 "사과","이유"는 제외
    if re.search(rf"[{_SINO_DIGIT}][{_UNIT_CHARS}]", s):
        return None
    s = re.sub(rf"[^\d.{_UNIT_CHARS}]", "", s)
    if not s:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        n = float(s)
        return str(int(n)) if n == int(n) else str(n)
    total = 0.0
    for unit_char, unit_val in _BIG:
        if unit_char in s:
            pre, s = s.split(unit_char, 1)
            total += _coeff(pre) * unit_val
    for m in re.finditer(r"(\d*(?:\.\d+)?)\s*([천백십])", s):
        total += float(m.group(1) or "1") * _SMALL[m.group(2)]
    plain = re.sub(r"[\d.]*[천백십]", "", s)
    plain = re.sub(r"[^\d.]", "", plain)
    if plain:
        try:
            total += float(plain)
        except ValueError:
            pass
    if total == 0.0:
        return None
    return str(int(total)) if total == int(total) else str(total)


def _parse_korean_numeral_rule(raw: str) -> str | None:
    """한자어·고유어 수사 규칙 파싱. 실패 시 None."""
    s = raw.strip()
    m = re.fullmatch(r"제\s*(\d+)", s)
    if m:
        return m.group(1)
    v = _parse_sino_with_units(s)   # 천/백/십 + 만/억/조/경 ("백이십만"→1200000)
    if v is not None:
        return str(v)
    v = _parse_native(s)
    if v is not None:
        return str(v)
    return None
