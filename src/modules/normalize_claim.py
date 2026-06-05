from __future__ import annotations

import re

from src.schemas.runtime import MasterSchema


class NormalizeClaimError(Exception):
    """클레임 정규화 실패 — 한국어 수치/시점 파싱 오류 등."""


# ── 상수 ──────────────────────────────────────────────────────────────────────

_BIG = [("경", 10**16), ("조", 10**12), ("억", 10**8), ("만", 10**4)]
_SMALL = {"천": 1_000, "백": 100, "십": 10}
_UNIT_CHARS = "만억조경천백십"

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

_INCREASE = re.compile(r"증가|상승|늘어|올라|증대|올랐|늘었")
_DECREASE = re.compile(r"감소|하락|줄어|내려|하강|감축|내렸|줄었")


def _fmt_decimal(x: float) -> str:
    """소수 표기. 유효숫자 4자리로 자르되 정수도 소수점(.0)을 유지한다.

    예: 1.0 → "1.0", 0.32 → "0.32", 0.005 → "0.005".
    """
    s = f"{x:.4g}"
    if "." not in s and "e" not in s and "E" not in s:
        s += ".0"
    return s


# ── ② 큰 수 단위 ──────────────────────────────────────────────────────────────

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


def _parse_number(raw: str) -> str | None:
    s = raw.strip().replace(",", "")
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


# ── ① 한글 수사 ───────────────────────────────────────────────────────────────

def _parse_sino(s: str) -> int | None:
    """한자어 수사 → 정수. "삼십이" → 32"""
    s = s.strip()
    # 서수 "제N" 처리
    m = re.fullmatch(r"제(\d+)", s)
    if m:
        return int(m.group(1))
    # 한자어 룩업
    result, current = 0, 0
    i = 0
    while i < len(s):
        matched = False
        for word in ("천", "백", "십"):
            if s[i:].startswith(word):
                val = _SINO[word]
                result += (current or 1) * val
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


def _parse_native(s: str) -> int | None:
    """고유어 수사 → 정수. "스물셋" → 23"""
    s = s.strip()
    # 서수 처리
    ordinals = {"첫째": 1, "둘째": 2, "셋째": 3, "넷째": 4, "다섯째": 5}
    if s in ordinals:
        return ordinals[s]
    # 십단위 먼저 (긴 것부터)
    tens_words = ["아흔", "여든", "일흔", "예순", "쉰", "마흔", "서른", "스무", "스물", "열"]
    units_words = ["아홉", "여덟", "일곱", "여섯", "다섯", "넷", "셋", "둘", "하나",
                   "네", "세", "두", "한"]
    tens, ones = 0, 0
    rest = s
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


def _try_korean_numeral(s: str) -> str | None:
    # 서수 "제N"
    m = re.fullmatch(r"제\s*(\d+)", s)
    if m:
        return m.group(1)
    # 한자어
    v = _parse_sino(s)
    if v is not None:
        return str(v)
    # 고유어
    v = _parse_native(s)
    if v is not None:
        return str(v)
    return None


# ── ④ 범위·한계 ───────────────────────────────────────────────────────────────

def _try_range(s: str) -> str | None:
    # 구간: "A부터 B까지" or "A~B"
    m = re.search(r"(.+?)\s*부터\s*(.+?)\s*까지", s)
    if m:
        a = _parse_number(m.group(1)) or m.group(1).strip()
        b = _parse_number(m.group(2)) or m.group(2).strip()
        return f"{a}~{b}"
    m = re.fullmatch(r"(\d[\d,.]*)~(\d[\d,.]*)", s.replace(" ", ""))
    if m:
        a = _parse_number(m.group(1)) or m.group(1)
        b = _parse_number(m.group(2)) or m.group(2)
        return f"{a}~{b}"

    # 단방향 경계
    patterns = [
        (r"(.+?)\s*이상", ">="),
        (r"(.+?)\s*이하", "<="),
        (r"(.+?)\s*초과", ">"),
        (r"(.+?)\s*미만", "<"),
        (r"최[대고]\s*(.+)", "<="),
        (r"최[소저]\s*(.+)", ">="),
    ]
    for pat, op in patterns:
        m = re.fullmatch(pat, s)
        if m:
            num = _parse_number(m.group(1)) or m.group(1).strip()
            return f"{op}{num}"
    return None


# ── ⑤ 증감·변화 ───────────────────────────────────────────────────────────────

def _try_change(s: str) -> str | None:
    # 배수: "2배", "갑절", "절반", "반"
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*배", s)
    if m:
        return str(float(m.group(1)))
    if s in ("갑절",):
        return "2.0"

    # 변화율: "3.2% 증가", "5% 감소", "1.5%p 상승", "2퍼센트포인트 하락"
    # 단위(%, %p, 퍼센트)는 extract 가 unit 으로 분리 → 여기선 부호+수치만 둔다.
    # %p vs % 구분은 claim.unit 이 보유(value 에 마커를 박지 않음).
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|퍼센트)", s)
    if m and (_INCREASE.search(s) or _DECREASE.search(s)):
        val = _fmt_decimal(float(m.group(1)))
        sign = "-" if _DECREASE.search(s) else "+"
        return f"{sign}{val}"

    # 방향만 있는 경우: "생산량 증가"
    if _INCREASE.search(s) and not re.search(r"\d", s):
        return "+"
    if _DECREASE.search(s) and not re.search(r"\d", s):
        return "-"

    return None


# ── ⑥ 비율·분수 ───────────────────────────────────────────────────────────────

def _try_ratio(s: str) -> str | None:
    # 비(比): "2 대 1"
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*대\s*(\d+(?:\.\d+)?)", s)
    if m:
        return f"{m.group(1)}:{m.group(2)}"

    # 할·푼·리·모
    _HAL = {"할": 0.1, "푼": 0.01, "리": 0.001, "모": 0.0001}
    hal_pat = re.compile(r"(\d+)\s*([할푼리모])")
    # "타율 3할 2푼" → prefix 제거 후 파싱
    stripped = re.sub(r"^[^\d할푼리모]*", "", s)
    hits = hal_pat.findall(stripped)
    if hits:
        total = sum(int(n) * _HAL[u] for n, u in hits)
        return f"{round(total, 4):.4g}"

    # 분수: "5분의 1"
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*분의\s*(\d+(?:\.\d+)?)", s)
    if m:
        denom, numer = float(m.group(1)), float(m.group(2))
        if denom == 0:
            return None
        val = numer / denom
        return f"{round(val, 4):.4g}"

    # 어림 비율
    approx = {"절반": "0.5", "반": "0.5", "과반": "0.5"}
    if s in approx:
        return approx[s]

    # 퍼센트: "32%" or "32퍼센트"
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:%|퍼센트)", s)
    if m:
        val = float(m.group(1)) / 100
        return _fmt_decimal(val)

    return None


# ── 메인 파서 ─────────────────────────────────────────────────────────────────

def _parse_value(raw: str) -> str:
    s = raw.strip()
    return (
        _try_range(s)
        or _try_change(s)
        or _try_ratio(s)
        or _try_korean_numeral(s)
        or _parse_number(raw)
        or raw
    )


# ── 시점 정규화 ───────────────────────────────────────────────────────────────

def _parse_base(base: str) -> tuple[int | None, int | None]:
    """기준 시점(기사 발행일 등) → (연, 월). 파싱 불가면 (None, None)."""
    m = re.match(r"(\d{4})(?:[-/.](\d{1,2}))?", base.strip())
    if not m:
        return None, None
    return int(m.group(1)), (int(m.group(2)) if m.group(2) else None)


def _normalize_period(raw: str, base: str = "") -> str:
    """시점 정규화. 상대 표현(전년/전월/전분기)은 base(기사 발행일) 기준 절대값으로.

    절대 표기 → "YYYY" | "YYYY-MM". 상대 표기 → "YYYY"(전년) | "YYYY-MM"(전월)
    | "YYYY-Qn"(전분기). base 가 없거나 파싱 불가면 상대 표현은 원문 그대로 둔다.
    """
    s = raw.strip()
    # 절대 표기: "YYYY년 [MM월]", "YYYY"
    m = re.match(r"(\d{4})년(?:\s*(\d{1,2})월)?", s)
    if m:
        year, month = m.group(1), m.group(2)
        return f"{year}-{int(month):02d}" if month else year
    if re.fullmatch(r"\d{4}", s):
        return s
    # 상대 표기: base(연·월) 기준 해석
    by, bm = _parse_base(base)
    if by is not None:
        if re.search(r"전년|작년|지난\s*해|전년도", s):
            return str(by - 1)
        if re.search(r"올해|금년|당해\s*연도", s):
            return str(by)
        if bm is not None and re.search(r"전월|전달|지난\s*달", s):
            y, mo = (by - 1, 12) if bm == 1 else (by, bm - 1)
            return f"{y}-{mo:02d}"
        if bm is not None and re.search(r"전분기|지난\s*분기", s):
            q = (bm - 1) // 3 + 1                       # 현재 분기
            y, q = (by - 1, 4) if q == 1 else (by, q - 1)
            return f"{y}-Q{q}"
    return raw


# ── 엔트리포인트 ──────────────────────────────────────────────────────────────

async def normalize_claim(master_schema: MasterSchema) -> None:
    """
    [3] Normalize Claim

    Input:  master_schema.claims[*].value.raw / period_value.raw
    Output: master_schema.claims[*].value.llm_value / period_value.llm_value

    한국어 수사·시점을 산술값으로 정규화한다.
    """
    article = getattr(master_schema, "article", None)
    base = article.published_at if article else ""  # 상대시점 해석 기준(기사 발행일)
    for claim in master_schema.claims:
        claim.value.llm_value = _parse_value(claim.value.raw)
        claim.period_value.llm_value = _normalize_period(claim.period_value.raw, base)
