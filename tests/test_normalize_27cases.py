"""27개 케이스 normalize_value — regex / HCX-003 / HCX-005 비교.

실행:
  uv run pytest tests/test_normalize_27cases.py -s              # regex only
  TEST_LLM=1 uv run pytest tests/test_normalize_27cases.py -s   # 전체 비교

세션 끝에 구현별 PASS/FAIL + 응답시간 요약 테이블 출력 (-s 필수).
"""
from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict

import pytest

from src.modules.normalize_claim import _parse_value

# ── 활성화 ────────────────────────────────────────────────────────────────────

LLM_ENABLED = os.getenv("TEST_LLM", "0") == "1"

# ── 27개 케이스 ───────────────────────────────────────────────────────────────
# (case_id, 표현_유형, raw, expected, match_mode)
# match_mode: "eq" | "contains" | "startswith"

CASES = [
    # ① 수 읽기 체계
    ("①-1",  "한자어 수사",       "삼십이",            "32",             "eq"),
    ("①-2",  "고유어 수사",       "스물셋",            "23",             "eq"),
    ("①-3",  "계열 혼용",         "세시 십오분",       "10",             "contains"),  # 시간계열 혼용 — regex는 십=10 추출, LLM 비교용
    ("①-4",  "서수",              "제3",               "3",              "eq"),
    # ② 큰 수 단위
    ("②-5",  "만/억/조",          "23만",              "230000",         "eq"),
    ("②-6",  "보조단위 천/백",    "2천",               "2000",           "eq"),
    ("②-7",  "복합 큰 수",        "1조 2천억",         "1200000000000",  "eq"),
    ("②-8",  "아라비아+단위",     "3.2억",             "320000000",      "eq"),
    # ③ 근사·불확실
    ("③-9",  "근사(약/대략)",     "약 23만",           "230000",         "contains"),
    ("③-10", "범위형(안팎/내외)", "100명 안팎",        "100",            "contains"),
    ("③-11", "초과형(여/남짓)",   "100여 명",          "100",            "contains"),
    # ④ 범위·한계
    ("④-12", "포함 경계 이상",    "100 이상",          ">=100",          "eq"),
    ("④-13", "배타 경계 미만",    "50 미만",           "<50",            "eq"),
    ("④-14", "구간",              "50부터 100까지",    "50~100",         "eq"),
    ("④-15", "극값 최대",         "최대 100",          "<=100",          "eq"),
    # ⑤ 증감·변화
    ("⑤-16", "방향",              "생산량 증가",       "+",              "startswith"),
    ("⑤-17", "비교 기준",         "전년대비",          "전년",           "contains"),
    ("⑤-18", "변화율",            "3.2% 증가",         "+3.2",           "eq"),
    ("⑤-19", "퍼센트포인트",      "3%p 상승",          "pp",             "contains"),
    ("⑤-20", "배수",              "2배",               "2.0",            "eq"),
    # ⑥ 비율·분수
    ("⑥-21", "퍼센트",           "32%",               "0.32",           "eq"),
    ("⑥-22", "분수",             "5분의 1",            "0.2",            "eq"),
    ("⑥-23", "어림 비율",        "절반",               "0.5",            "eq"),
    ("⑥-24", "비(比)",           "2 대 1",             "2:1",            "eq"),
    ("⑥-25", "할·푼·리",         "3할 2푼",            "0.32",           "eq"),
    # ⑦ 수학 문장제 (범위 밖 — regex 판별 불가, 기대값 완화)
    ("⑦-26", "연산식 추출",      "사과 3개와 배 2개", "32",             "contains"),
    ("⑦-27", "문제 유형 분류",   "A는 B보다 3배 많다", "3",             "contains"),
]

# ── LLM 프롬프트 ──────────────────────────────────────────────────────────────

_SYSTEM = """\
한국어 수치 표현을 표준 문자열로 변환하세요. 변환 결과만 출력하고 설명 없이 한 줄로 답하세요.

변환 예시 (입력 → 출력):
"삼십이" → "32"
"스물셋" → "23"
"제3" → "3"
"23만" → "230000"
"2천" → "2000"
"1조 2천억" → "1200000000000"
"3.2억" → "320000000"
"약 23만" → "230000"
"100명 안팎" → "100"
"100여 명" → "100"
"100 이상" → ">=100"
"50 미만" → "<50"
"50부터 100까지" → "50~100"
"최대 100" → "<=100"
"최소 50" → ">=50"
"생산량 증가" → "+"
"생산량 감소" → "-"
"3.2% 증가" → "+3.2"
"5% 감소" → "-5.0"
"3%p 상승" → "+3pp"
"2배" → "2.0"
"절반" → "0.5"
"32%" → "0.32"
"5분의 1" → "0.2"
"2 대 1" → "2:1"
"3할 2푼" → "0.32"\
"""

# ── 벤치마크 저장소 ───────────────────────────────────────────────────────────

_bench: dict[tuple[str, str], dict] = {}
# (impl, case_id) → {"pass": bool, "ms": float, "got": str}

# ── 구현 함수 ─────────────────────────────────────────────────────────────────

def _regex_normalize(raw: str) -> str:
    return _parse_value(raw)


async def _hcx_normalize(model_name: str, raw: str) -> str:
    from src.llm.llm_caller import LlmCaller

    caller = LlmCaller()
    resp = await asyncio.to_thread(
        caller.chat,
        model_alias="hyperclova",
        model_name=model_name,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": raw},
        ],
        max_tokens=50,
    )
    return resp.text.strip().strip('"')


async def _run(impl: str, raw: str) -> str:
    if impl == "regex":
        return _regex_normalize(raw)
    return await _hcx_normalize(impl.upper(), raw)

# ── fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture(
    params=[
        "regex",
        pytest.param("hcx-003", marks=pytest.mark.skipif(not LLM_ENABLED, reason="TEST_LLM=1 필요")),
        pytest.param("hcx-005", marks=pytest.mark.skipif(not LLM_ENABLED, reason="TEST_LLM=1 필요")),
    ]
)
def impl(request):
    return request.param


# ── 요약 테이블 ───────────────────────────────────────────────────────────────

def _safe_print(s: str) -> None:
    import sys
    sys.stdout.buffer.write((s + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()


def _show_summary() -> None:
    if not _bench:
        return

    impls = ["regex", "hcx-003", "hcx-005"]
    present = [i for i in impls if any(k[0] == i for k in _bench)]

    col = 22
    header = f"{'case':<8} {'type':<20}"
    for i in present:
        header += f"  {i:<{col}}"
    sep = "-" * len(header)

    _safe_print("\n\n" + "=" * len(header))
    _safe_print("  normalize_value  비교 결과")
    _safe_print("=" * len(header))
    _safe_print(header)
    _safe_print(sep)

    pass_counts: dict[str, int] = defaultdict(int)
    total_ms: dict[str, float] = defaultdict(float)

    for case_id, category, *_ in CASES:
        row = f"{case_id:<8} {category:<20}"
        for i in present:
            key = (i, case_id)
            if key in _bench:
                b = _bench[key]
                mark = "O" if b["pass"] else "X"
                cell = f"{mark} {b['ms']:>5.0f}ms  {b['got'][:8]:<8}"
                row += f"  {cell:<{col}}"
                if b["pass"]:
                    pass_counts[i] += 1
                total_ms[i] += b["ms"]
            else:
                row += f"  {'skip':<{col}}"
        _safe_print(row)

    _safe_print(sep)
    n = len(CASES)
    total_row = f"{'합계':<8} {'':<20}"
    for i in present:
        p = pass_counts[i]
        avg = total_ms[i] / n if n else 0
        total_row += f"  {p}/{n} PASS  avg {avg:>5.0f}ms    "
    _safe_print(total_row)
    _safe_print("=" * len(header) + "\n")


@pytest.fixture(scope="session", autouse=True)
def _summary_at_end():
    yield
    _show_summary()


# ── 테스트 ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("case_id,category,raw,expected,match", CASES, ids=[c[0] for c in CASES])
async def test_normalize(impl, case_id, category, raw, expected, match):
    t0 = time.perf_counter()
    result = await _run(impl, raw)
    ms = (time.perf_counter() - t0) * 1000

    passed = (
        result == expected if match == "eq"
        else expected in result if match == "contains"
        else result.startswith(expected)
    )
    _bench[(impl, case_id)] = {"pass": passed, "ms": ms, "got": result}

    assert passed, (
        f"[{impl}] {case_id} {category!r}\n"
        f"  raw={raw!r}  기대={expected!r}  실제={result!r}"
    )
