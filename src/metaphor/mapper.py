"""비유비교 매핑 — "여의도 면적의 3배" → 실수치(8.7㎢) 환산.

사전(loader)의 기준물 별칭을 문장에서 찾고, 직후 표현에서 배수를 해석해
resolved_value = 기준값 × 배수 를 만든다. claim_type=METAPHORIC 주장을
검증 가능한 수치로 바꾸는 용도.

배수 표현이 없는 단순 지명 언급("여의도 증권가")은 매칭하지 않는다(오탐 방지).
지원 배수: N배 / 한·두·세…배 / N분의 M / 절반 / N개·바퀴·마리(수량사) /
달하는·맞먹는·만 한 등 동급 표현(=1배). "배 반"·"바퀴 반"의 반은 +0.5.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.metaphor.loader import MetaphorEntry, load_entries

# 별칭 매칭 위치 이후 배수 표현을 찾는 범위(자)
_WINDOW = 24

# 별칭과 배수 사이 연결어: "여의도[ 면적][의] [약 ]3배"
_DIM = r"(?:\s*(?:면적|넓이|크기|규모|높이|길이|무게|부피|거리|둘레))?"
_CONNECT = rf"{_DIM}(?:의)?\s*(?:약|무려|거의)?\s*"

_NATIVE_NUM = {
    "한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5,
    "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10, "스무": 20,
}
_NATIVE_ALT = "|".join(_NATIVE_NUM)

_HALF_SUFFIX = r"(\s*반)?"  # "3배 반", "한 바퀴 반"

_RE_FRACTION = re.compile(rf"^{_CONNECT}(\d+)\s*분의\s*(\d+)")
_RE_TIMES_DIGIT = re.compile(rf"^{_CONNECT}(\d[\d,]*(?:\.\d+)?)\s*배{_HALF_SUFFIX}")
_RE_TIMES_NATIVE = re.compile(rf"^{_CONNECT}({_NATIVE_ALT})\s*배{_HALF_SUFFIX}")
_RE_HALF = re.compile(rf"^{_CONNECT}절반")
# 동급 표현(=1배). 수량 표현이 모두 실패했을 때만 시도한다.
_RE_EQUAL = re.compile(
    rf"^(?:{_DIM}\s*(?:에|와|과)?\s*(?:달하|이르|해당하|맞먹|육박)|만\s?한)"
)


@dataclass(frozen=True)
class MetaphorMatch:
    """비유비교 매칭 1건. resolved_value 단위는 entry.unit."""

    entry: MetaphorEntry
    matched_text: str
    multiplier: float
    resolved_value: float
    unit: str


def _counter_patterns(entry: MetaphorEntry) -> list[re.Pattern[str]]:
    """수량사 패턴 — "축구장 [약 ]70개", "지구 두 바퀴"."""
    alt = "|".join(re.escape(c) for c in entry.counters)
    return [
        re.compile(rf"^\s*(?:약|무려|거의)?\s*(\d[\d,]*(?:\.\d+)?)\s*(?:{alt}){_HALF_SUFFIX}"),
        re.compile(rf"^\s*(?:약|무려|거의)?\s*({_NATIVE_ALT})\s*(?:{alt}){_HALF_SUFFIX}"),
    ]


def _parse_multiplier(window: str, entry: MetaphorEntry) -> tuple[float, int] | None:
    """별칭 직후 텍스트에서 배수 해석. (배수, 소비한 길이) 또는 None."""
    m = _RE_FRACTION.match(window)
    if m:
        return int(m.group(2)) / int(m.group(1)), m.end()
    m = _RE_TIMES_DIGIT.match(window)
    if m:
        mult = float(m.group(1).replace(",", "")) + (0.5 if m.group(2) else 0.0)
        return mult, m.end()
    m = _RE_TIMES_NATIVE.match(window)
    if m:
        return _NATIVE_NUM[m.group(1)] + (0.5 if m.group(2) else 0.0), m.end()
    for pat in _counter_patterns(entry):
        m = pat.match(window)
        if m:
            raw = m.group(1)
            base = _NATIVE_NUM.get(raw) or float(raw.replace(",", ""))
            return base + (0.5 if m.group(2) else 0.0), m.end()
    m = _RE_HALF.match(window)
    if m:
        return 0.5, m.end()
    m = _RE_EQUAL.match(window)
    if m:
        return 1.0, m.end()
    return None


def find_metaphors(
    text: str, path: Path | str | None = None
) -> list[MetaphorMatch]:
    """문장 전체에서 비유비교를 모두 찾는다(앞에서부터, 겹침 없이)."""
    entries = load_entries(path)
    by_alias = {a: e for e in entries for a in e.aliases}
    # 같은 위치에선 긴 별칭 우선("여의도 면적" > "여의도").
    # (?<!\w): "성남산업단지"의 "남산" 같은 합성어 내부 오탐 차단.
    alias_re = re.compile(
        r"(?<!\w)(?:"
        + "|".join(re.escape(a) for a in sorted(by_alias, key=len, reverse=True))
        + ")"
    )
    matches: list[MetaphorMatch] = []
    consumed_end = 0
    for am in alias_re.finditer(text):
        if am.start() < consumed_end:
            continue
        entry = by_alias[am.group()]
        parsed = _parse_multiplier(text[am.end(): am.end() + _WINDOW], entry)
        if parsed is None:
            continue  # 배수 표현 없는 단순 언급 — 매칭하지 않음
        mult, used = parsed
        end = am.end() + used
        matches.append(
            MetaphorMatch(
                entry=entry,
                matched_text=text[am.start(): end],
                multiplier=mult,
                resolved_value=round(entry.value * mult, 6),
                unit=entry.unit,
            )
        )
        consumed_end = end
    return matches


def map_metaphor(text: str, path: Path | str | None = None) -> MetaphorMatch | None:
    """첫 번째 비유비교 매칭만 반환(없으면 None)."""
    found = find_metaphors(text, path)
    return found[0] if found else None
