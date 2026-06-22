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
    _parse_korean_numeral_rule,
    _parse_number_rule,
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

_INCREASE = re.compile(r"증가|급증|상승|늘어|올라|올랐|오를|증대|늘었")
_DECREASE = re.compile(r"감소|급감|하락|줄어|내려|하강|감축|내렸|줄었|낮췄|낮아졌")

# native 수사(관형사형) 배수 — "두 배"=2.0 (아라비아 "2배" 와 parity).
_NATIVE_MULT = {
    "한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5,
    "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10,
}


def _fmt_decimal(x: float) -> str:
    # 유효숫자 4자리 포맷. 정수에 .0 을 붙이지 않는다(룰 경로와 표현 통일: 49%→"49").
    return f"{x:.4g}"


def _try_range(s: str) -> str | None:
    m = re.search(r"(.+?)\s*부터\s*(.+?)\s*까지", s)
    if m:
        a = _parse_number_rule(m.group(1)) or m.group(1).strip()
        b = _parse_number_rule(m.group(2)) or m.group(2).strip()
        return f"{a}~{b}"
    # 틸드 범위 — 단위 접미사(원·만·억·%)가 붙어도 양쪽을 각각 파싱한다.
    # 예: "1850~1950원"→"1850~1950", "100만~200만"→"1000000~2000000".
    if "~" in s:
        parts = s.split("~")
        if len(parts) == 2 and all(re.search(r"\d", p) for p in parts):
            a = _parse_number_rule(parts[0]) or parts[0].strip()
            b = _parse_number_rule(parts[1]) or parts[1].strip()
            return f"{a}~{b}"
    patterns = [
        (r"(.+?)\s*이상", ">="), (r"(.+?)\s*이하", "<="),
        (r"(.+?)\s*초과", ">"),  (r"(.+?)\s*미만", "<"),
        (r"최[대고]\s*(.+)", "<="), (r"최[소저]\s*(.+)", ">="),
    ]
    # 종결어미(이다·이라 등)가 붙어도 이상/이하/초과/미만을 포착하도록 허용.
    end = r"(?:\s*(?:이다|이라|입니다|임|였다|이었다))?"
    for pat, op in patterns:
        m = re.fullmatch(pat + end, s)
        if m:
            num = _parse_number_rule(m.group(1)) or m.group(1).strip()
            return f"{op}{num}"
    return None


def _try_change(s: str) -> str | None:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*배", s)
    if m:
        return str(float(m.group(1)))
    m = re.fullmatch(r"(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*배", s)
    if m:
        return str(float(_NATIVE_MULT[m.group(1)]))
    if s in ("갑절",):
        return "2.0"
    inc, dec = _INCREASE.search(s), _DECREASE.search(s)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|퍼센트)", s)
    if m and (inc or dec):
        val = _fmt_decimal(float(m.group(1)))
        return f"{'-' if dec else '+'}{val}"
    # 단위(만·억·원·명·포인트 등) 동반 증감 — 수치를 파싱해 방향 부호를 붙인다.
    # 예: "21만6000명 증가"→"+216000", "2290억원 줄었다"→"-229000000000".
    if (inc or dec) and re.search(r"\d", s):
        num = _parse_number_rule(s)
        if num is not None:
            return f"{'-' if dec else '+'}{num}"
    if inc and not re.search(r"\d", s):
        return "+"
    if dec and not re.search(r"\d", s):
        return "-"
    return None


def _try_ratio(s: str) -> str | None:
    # 단위·접미사(비율 등)가 붙어도 매칭되도록 search. "3대 5 비율"→"3:5".
    m = re.search(r"(\d+(?:\.\d+)?)\s*대\s*(\d+(?:\.\d+)?)", s)
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    _HAL = {"할": 0.1, "푼": 0.01, "리": 0.001, "모": 0.0001}
    hal_pat = re.compile(r"(\d+)\s*([할푼리모])")
    stripped = re.sub(r"^[^\d할푼리모]*", "", s)
    hits = hal_pat.findall(stripped)
    if hits:
        total = sum(int(n) * _HAL[u] for n, u in hits)
        return f"{round(total, 4):.4g}"
    # "N분의M" = M/N. 접미사 허용(search). "3분의 1"→"0.3333".
    m = re.search(r"(\d+(?:\.\d+)?)\s*분의\s*(\d+(?:\.\d+)?)", s)
    if m:
        denom, numer = float(m.group(1)), float(m.group(2))
        if denom == 0:
            return None
        return f"{round(numer / denom, 4):.4g}"
    # "A/B" 분수 = A/B. 분자·분모 1~2자리 + 'YYYY/MM(/DD)' 날짜(4자리 연도)는 제외.
    # 예: "1/3"→"0.3333"; "2025/03"·"2024/12/31"→매칭 안 함.
    m = re.search(r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)", s)
    if m and not re.search(r"\d{4}\s*/\s*\d{1,2}", s):
        numer, denom = int(m.group(1)), int(m.group(2))
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


def _parse_value(raw: str) -> str | None:
    """수치 룰 베이스 정규화 (전부 동기·LLM 무관). 모든 룰 실패 시 None.

    룰을 먼저 전부 시도한다. LLM 폴백은 _resolve_value 에서 단 한 번만 호출한다 —
    예전엔 parse_korean_numeral 의 LLM 폴백이 parse_number 룰보다 먼저 끼어들어
    '아라비아+만' 수치를 환각 오스케일(×10/×100/×1000)하던 문제가 있었다.
    """
    s = raw.strip()
    return (
        _try_range(s)
        or _try_change(s)
        or _try_ratio(s)
        or _parse_korean_numeral_rule(s)
        or _parse_number_rule(raw)
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

    # 슬래시·점 날짜 YYYY/MM·YYYY.MM(·/DD) → YYYY-MM
    # (?!\s*분기): "2024.4분기" 를 4월로 오타입하지 않도록 분기 표기는 제외(아래 분기 룰로 위임).
    m = re.match(r"(\d{4})\s*[/.]\s*(\d{1,2})(?!\s*분기)", s)
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

    # YYYY 회계연도 → 연도만 (YYYY년과 동일 처리)
    m = re.match(r"(\d{4})\s*회계연도", s)
    if m:
        return m.group(1)

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

    # 이전 계열 — 세부 패턴(동월·동기·분기·반기·말·초)을 포괄 연도 분기보다 먼저 매칭
    if re.search(r"재작년|지지난\s*해", s):
        return str(by - 2)

    m = re.search(r"(?:작년|전년|지난\s*해)\s*(\d{1,2})월", s)
    if m:
        return f"{by - 1}-{int(m.group(1)):02d}"

    m = re.search(r"지난\s*(\d{1,2})월", s)
    if m:
        return f"{by}-{int(m.group(1)):02d}"

    if re.search(r"(?:전년|작년|지난\s*해)\s*동월", s):
        return f"{by - 1}-{bm:02d}" if bm else None

    if re.search(r"(?:전년|작년|지난\s*해)\s*동기", s):
        return f"{by - 1}-Q{(bm - 1) // 3 + 1}" if bm else None

    m = re.search(r"(?:작년|전년|지난\s*해)\s*([1-4])분기", s)
    if m:
        return f"{by - 1}-Q{m.group(1)}"

    if re.search(r"(?:작년|전년|지난\s*해)\s*상반기", s):
        return f"{by - 1}-H1"

    if re.search(r"(?:작년|전년|지난\s*해)\s*하반기", s):
        return f"{by - 1}-H2"

    if re.search(r"(?:작년|전년|지난\s*해)\s*말", s):
        return f"{by - 1}-12"

    if re.search(r"(?:작년|전년|지난\s*해)\s*초", s):
        return f"{by - 1}-01"

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

    # 현재 계열 — 세부(올해 N월·N분기)를 포괄 연도 분기보다 먼저 매칭
    m = re.search(r"(?:올해|금년|당해|이번\s*해|올)\s*(\d{1,2})월", s)
    if m:
        return f"{by}-{int(m.group(1)):02d}"

    # 연도 없는 N분기(1분기·올 1분기·지난 1분기) — 절대·작년 분기는 위에서 이미 처리됨
    m = re.search(r"([1-4])\s*분기", s)
    if m:
        return f"{by}-Q{m.group(1)}"

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
    if re.search(r"(?:올해|금년|당해|이번\s*해)\s*말|연말", s):
        return f"{by}-12"

    m = re.search(r"(\d{4})년\s*초", s)
    if m:
        return f"{m.group(1)}-01"
    if re.search(r"(?:올해|금년|당해|이번\s*해)\s*초|연초", s):
        return f"{by}-01"

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
    result = _parse_value(raw)                     # 룰 전부 시도(동기)
    if result is None:
        result = await _llm_normalize_value(raw)   # 전부 실패 시에만 LLM 1회
    return result


_ABS_YEAR = re.compile(r"\d{4}")
_NEEDS_MONTH = re.compile(r"달|월|분기|반기")
_DAY_ONLY = re.compile(r"\d{1,2}\s*일")


def _llm_fallback_allowed(raw: str, base: str) -> bool:
    """base 부족·표현 불가 시점은 LLM 폴백 차단 — 그럴듯한 환각 채택 방지."""
    if _ABS_YEAR.search(raw):
        return True                          # 절대 연도 포함 → base 불필요
    by, bm = _parse_base(base)
    if by is None:
        return False                         # 상대 표현인데 기준 연도 없음
    if bm is None and _NEEDS_MONTH.search(raw):
        return False                         # 월 단위 해소 필요한데 기준 월 없음
    if _DAY_ONLY.search(raw) and not _NEEDS_MONTH.search(raw):
        return False                         # 일 단위 — 표준 형식(Y/M/Q/H)으로 표현 불가
    return True


async def _resolve_period(raw: str, base: str) -> str:
    result = _normalize_period(raw, base)
    if result is None and _llm_fallback_allowed(raw, base):
        result = await _llm_normalize_period(raw, base)
    return result if result is not None else raw


# ── 엔트리포인트 ──────────────────────────────────────────────────────────────

async def _normalize_one(claim: Claim, base: str) -> None:
    """claim 1건 정규화. value·주 시점은 병렬, 비교 기준 시점은 주 시점 기준으로 후처리.

    '전년 동월/전분기/전년 대비' 같은 비교 기준은 발행일이 아니라 **주 시점(period)** 에서
    빼야 한다(2025-03 의 '전년 동월' = 2024-03). 그래서 주 시점을 먼저 정규화하고 그 값을
    base 로 삼아 compare_period 를 푼다(발행일 base 면 발행월 기준으로 어긋남 → 증감 NEI).
    """
    claim.value.llm_value, claim.period_value.llm_value = await asyncio.gather(
        _resolve_value(claim.value.raw),
        _resolve_period(claim.period_value.raw, base),
    )
    if claim.compare_period_value:
        cmp_base = claim.period_value.llm_value or base
        claim.compare_period_value.llm_value = await _resolve_period(
            claim.compare_period_value.raw, cmp_base
        )


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
