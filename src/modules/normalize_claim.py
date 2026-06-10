"""claim 슬롯 정규화 — value · period_value · compare_period_value.

수치·시점을 표준값으로 정규화한다.
룰 베이스 실패(None 반환) 시 LLM 폴백을 호출한다.
"""
from __future__ import annotations

import asyncio
import re

from src.llm.client import LlmError
from src.llm.model_presets import NORMALIZE_PERIOD, NORMALIZE_VALUE
from src.modules.parse_korean_number import (
    _parse_number_rule,
    parse_korean_numeral,
    parse_number,
)
from src.observability.tracing import traced_chat
from src.prompts.prompts import (
    NORMALIZE_PERIOD_SYSTEM,
    NORMALIZE_PERIOD_USER,
    NORMALIZE_VALUE_SYSTEM,
    NORMALIZE_VALUE_USER,
)
from src.schemas.runtime import Claim, MasterSchema


class NormalizeClaimError(Exception):
    """클레임 정규화 실패."""


# ── 수치 정규화 ────────────────────────────────────────────────────────────────

_INCREASE = re.compile(r"증가|상승|늘어|올라|증대|올랐|늘었")
_DECREASE = re.compile(r"감소|하락|줄어|내려|하강|감축|내렸|줄었|낮췄|낮아졌")


def _fmt_decimal(x: float) -> str:
    s = f"{x:.4g}"
    if "." not in s and "e" not in s and "E" not in s:
        s += ".0"
    return s


def _try_range(s: str) -> str | None:
    m = re.search(r"(.+?)\s*부터\s*(.+?)\s*까지", s)
    if m:
        a = _parse_number_rule(m.group(1)) or m.group(1).strip()
        b = _parse_number_rule(m.group(2)) or m.group(2).strip()
        return f"{a}~{b}"
    m = re.fullmatch(r"(\d[\d,.]*)~(\d[\d,.]*)", s.replace(" ", ""))
    if m:
        a = _parse_number_rule(m.group(1)) or m.group(1)
        b = _parse_number_rule(m.group(2)) or m.group(2)
        return f"{a}~{b}"
    patterns = [
        (r"(.+?)\s*이상", ">="), (r"(.+?)\s*이하", "<="),
        (r"(.+?)\s*초과", ">"),  (r"(.+?)\s*미만", "<"),
        (r"최[대고]\s*(.+)", "<="), (r"최[소저]\s*(.+)", ">="),
    ]
    for pat, op in patterns:
        m = re.fullmatch(pat, s)
        if m:
            num = _parse_number_rule(m.group(1)) or m.group(1).strip()
            return f"{op}{num}"
    return None


def _try_change(s: str) -> str | None:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*배", s)
    if m:
        return str(float(m.group(1)))
    if s in ("갑절",):
        return "2.0"
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|퍼센트)", s)
    if m and (_INCREASE.search(s) or _DECREASE.search(s)):
        val = _fmt_decimal(float(m.group(1)))
        sign = "-" if _DECREASE.search(s) else "+"
        return f"{sign}{val}"
    if _INCREASE.search(s) and not re.search(r"\d", s):
        return "+"
    if _DECREASE.search(s) and not re.search(r"\d", s):
        return "-"
    return None


def _try_ratio(s: str) -> str | None:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*대\s*(\d+(?:\.\d+)?)", s)
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    _HAL = {"할": 0.1, "푼": 0.01, "리": 0.001, "모": 0.0001}
    hal_pat = re.compile(r"(\d+)\s*([할푼리모])")
    stripped = re.sub(r"^[^\d할푼리모]*", "", s)
    hits = hal_pat.findall(stripped)
    if hits:
        total = sum(int(n) * _HAL[u] for n, u in hits)
        return f"{round(total, 4):.4g}"
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*분의\s*(\d+(?:\.\d+)?)", s)
    if m:
        denom, numer = float(m.group(1)), float(m.group(2))
        if denom == 0:
            return None
        return f"{round(numer / denom, 4):.4g}"
    approx = {"절반": "0.5", "반": "0.5", "과반": "0.5"}
    if s in approx:
        return approx[s]
    # % 값은 KOSIS(% 스케일: 3.1) 와 맞춰야 하므로 소수변환(÷100) 하지 않는다.
    # "3%"→"3", "3.1%"→"3.1" (단위 % 는 claim.unit 에 별도 보존).
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:%|퍼센트)", s)
    if m:
        return _fmt_decimal(float(m.group(1)))
    return None


async def _parse_value(raw: str) -> str | None:
    """수치 룰 베이스 정규화. 실패 시 None."""
    s = raw.strip()
    return (
        _try_range(s)
        or _try_change(s)
        or _try_ratio(s)
        or await parse_korean_numeral(s)
        or await parse_number(raw)
    )


# ── 시점 정규화 ────────────────────────────────────────────────────────────────

def _parse_base(base: str) -> tuple[int | None, int | None]:
    """발행일 문자열 → (연, 월). 파싱 불가 시 (None, None)."""
    m = re.match(r"(\d{4})(?:[-/.](\d{1,2}))?", base.strip())
    if not m:
        return None, None
    return int(m.group(1)), (int(m.group(2)) if m.group(2) else None)


def _month_offset(by: int, bm: int, n: int) -> str:
    """기준 연월에서 n개월 뺀 결과 → 'YYYY-MM'."""
    total = by * 12 + bm - 1 - n
    return f"{total // 12}-{total % 12 + 1:02d}"


def _normalize_period(raw: str, base: str = "") -> str | None:
    """시점 룰 베이스 정규화. 실패 시 None."""
    s = raw.strip()

    # ── 절대 표기 (구체적 패턴 먼저) ───────────────────────────────────────────
    m = re.match(r"(\d{4})년\s*(\d{1,2})월", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"

    m = re.match(r"(\d{4})년?\s*([1-4])분기", s)
    if m:
        return f"{m.group(1)}-Q{m.group(2)}"

    m = re.match(r"(\d{4})년?\s*상반기", s)
    if m:
        return f"{m.group(1)}-H1"

    m = re.match(r"(\d{4})년?\s*하반기", s)
    if m:
        return f"{m.group(1)}-H2"

    # YYYY년 이후/이전/부터/까지 → 연도만
    m = re.match(r"(\d{4})년?\s*(?:이후|이전|부터|까지)", s)
    if m:
        return m.group(1)

    # YYYY년 단독 또는 YYYY 4자리
    if re.fullmatch(r"\d{4}", s):
        return s

    m = re.fullmatch(r"(\d{4})년?", s)
    if m:
        return m.group(1)

    # ── base 의존 상대 표기 ────────────────────────────────────────────────────
    by, bm = _parse_base(base)
    if by is None:
        return None

    # 이전 계열
    m = re.search(r"(?:작년|전년|지난\s*해)\s*(\d{1,2})월", s)
    if m:
        return f"{by - 1}-{int(m.group(1)):02d}"

    m = re.search(r"지난\s*(\d{1,2})월", s)
    if m:
        return f"{by}-{int(m.group(1)):02d}"

    if re.search(r"전년|작년|지난\s*해|전년도|전해", s):
        return str(by - 1)

    if re.search(r"전월|전달|지난\s*달", s):
        return _month_offset(by, bm, 1) if bm else None

    if re.search(r"전분기|지난\s*분기", s):
        if bm is None:
            return None
        q = (bm - 1) // 3 + 1
        y, q = (by - 1, 4) if q == 1 else (by, q - 1)
        return f"{y}-Q{q}"

    # 동월/동기
    if re.search(r"(?:전년|작년|지난\s*해)\s*동월", s):
        return f"{by - 1}-{bm:02d}" if bm else None

    if re.search(r"(?:전년|작년|지난\s*해)\s*동기", s):
        return f"{by - 1}-Q{(bm - 1) // 3 + 1}" if bm else None

    # 현재 계열
    if re.search(r"올해|금년|당해|이번\s*해|금해", s):
        return str(by)

    if re.search(r"이번\s*달|이번달|금월|당월|이달", s):
        return f"{by}-{bm:02d}" if bm else str(by)

    if re.search(r"이번\s*분기|이번분기|당기|금기", s):
        return f"{by}-Q{(bm - 1) // 3 + 1}" if bm else None

    # 반기 이전 계열
    if re.search(r"전반기|지난\s*반기", s):
        if bm is None:
            return None
        return f"{by - 1}-H2" if bm <= 6 else f"{by}-H1"

    # 반기 현재 계열
    if re.search(r"이번\s*반기|이번반기|당반기|금반기", s):
        if bm is None:
            return None
        return f"{by}-H{'1' if bm <= 6 else '2'}"

    if re.search(r"(?:이번\s*)?상반기|금상반기|당상반기", s):
        return f"{by}-H1"

    if re.search(r"(?:이번\s*)?하반기|금하반기|당하반기", s):
        return f"{by}-H2"

    # N년 전/후
    m = re.search(r"(\d+)\s*년\s*전", s)
    if m:
        return str(by - int(m.group(1)))

    m = re.search(r"(\d+)\s*년\s*후", s)
    if m:
        return str(by + int(m.group(1)))

    # N개월 전
    m = re.search(r"(\d+)\s*개월\s*전", s)
    if m:
        return _month_offset(by, bm, int(m.group(1))) if bm else None

    # 연말/연초
    m = re.search(r"(\d{4})년\s*말", s)
    if m:
        return f"{m.group(1)}-12"
    if re.search(r"(?:작년|전년|지난\s*해)\s*말", s):
        return f"{by - 1}-12"
    if re.search(r"(?:올해|금년|당해|이번\s*해)\s*말|연말", s):
        return f"{by}-12"

    m = re.search(r"(\d{4})년\s*초", s)
    if m:
        return f"{m.group(1)}-01"
    if re.search(r"(?:올해|금년|당해|이번\s*해)\s*초|연초", s):
        return f"{by}-01"
    if re.search(r"(?:작년|전년|지난\s*해)\s*초", s):
        return f"{by - 1}-01"

    return None  # 패턴 미매칭 → LLM 폴백


# ── LLM 폴백 ──────────────────────────────────────────────────────────────────

async def _llm_normalize_value(raw: str) -> str:
    """수치 LLM 폴백. 실패 시 원문 반환."""
    messages = [
        {"role": "system", "content": NORMALIZE_VALUE_SYSTEM},
        {"role": "user",   "content": NORMALIZE_VALUE_USER.format(raw=raw)},
    ]
    try:
        response = await asyncio.to_thread(
            traced_chat,
            model_alias=NORMALIZE_VALUE.model_alias,
            model_name=NORMALIZE_VALUE.model_name,
            messages=messages,
            max_tokens=NORMALIZE_VALUE.max_tokens,
            trace_name="normalize_claim:value_llm",
        )
        return response.text.strip() or raw
    except (LlmError, AttributeError):
        return raw


async def _llm_normalize_period(raw: str, base: str) -> str:
    """시점 LLM 폴백. 실패 시 원문 반환."""
    messages = [
        {"role": "system", "content": NORMALIZE_PERIOD_SYSTEM},
        {"role": "user",   "content": NORMALIZE_PERIOD_USER.format(base=base, raw=raw)},
    ]
    try:
        response = await asyncio.to_thread(
            traced_chat,
            model_alias=NORMALIZE_PERIOD.model_alias,
            model_name=NORMALIZE_PERIOD.model_name,
            messages=messages,
            max_tokens=NORMALIZE_PERIOD.max_tokens,
            trace_name="normalize_claim:period_llm",
        )
        result = response.text.strip()
        if re.fullmatch(r"\d{4}(?:-\d{2}|-Q[1-4]|-H[12])?", result):
            return result
    except (LlmError, AttributeError):
        pass
    return raw


# ── resolve (룰 베이스 → LLM 폴백) ───────────────────────────────────────────

async def _resolve_value(raw: str) -> str:
    result = await _parse_value(raw)
    if result is None:
        result = await _llm_normalize_value(raw)
    return result


async def _resolve_period(raw: str, base: str) -> str:
    result = _normalize_period(raw, base)
    if result is None:
        result = await _llm_normalize_period(raw, base)
    return result


# ── 엔트리포인트 ──────────────────────────────────────────────────────────────

async def _normalize_one(claim: Claim, base: str) -> None:
    """claim 1건 정규화. value·period·compare_period 병렬 처리."""
    tasks: list = [
        _resolve_value(claim.value.raw),
        _resolve_period(claim.period_value.raw, base),
    ]
    if claim.compare_period_value:
        tasks.append(_resolve_period(claim.compare_period_value.raw, base))

    results = await asyncio.gather(*tasks)
    claim.value.llm_value        = results[0]
    claim.period_value.llm_value = results[1]
    if claim.compare_period_value:
        claim.compare_period_value.llm_value = results[2]


async def normalize_claim(master_schema: MasterSchema) -> None:
    """
    [3] Normalize Claim

    Input:  master_schema.claims[*].value.raw
                                   .period_value.raw
                                   .compare_period_value.raw
    Output: master_schema.claims[*].value.llm_value
                                   .period_value.llm_value
                                   .compare_period_value.llm_value

    수치·시점을 표준값으로 정규화한다.
    룰 베이스 실패 시 LLM 폴백. 모든 claim 병렬 처리.
    """
    article = getattr(master_schema, "article", None)
    published = article.published_at if article else None
    base = published if isinstance(published, str) else ""
    await asyncio.gather(*[_normalize_one(c, base) for c in master_schema.claims])
