"""경제성장률 기사 본문으로 normalize_claim 수동 검증.

테스트 기사:
  한국은행은 올해 경제성장률 전망치를 기존 1.9%에서 1.5%로 낮췄다.
  과거 30년간 1.5%보다 낮았던 때는 1998년, 2009년, 2020년이다.

실행:
  uv run pytest tests/260608_3_normalize-gdp-article_innnn.py -s -v
"""
from __future__ import annotations

import pytest

from src.modules.normalize_claim import _normalize_period, _parse_value

BASE = "2026-06-08"


async def run(value_raw: str, period_raw: str | None = None):
    v = await _parse_value(value_raw)
    p = _normalize_period(period_raw, BASE) if period_raw else ""
    return v, p


# ── 케이스 정의 ────────────────────────────────────────────────────────────────
# (case_id, 설명, value_raw, period_raw, expected_value, expected_period)
# expected 가 None 이면 해당 항목 검증 생략

CASES = [
    # ① LLM이 최종값만 추출했을 때
    ("V-01", "전망치 최종값 1.5%",
     "1.5%",        "올해",
     "0.015",       "2026"),

    # ② LLM이 이전값만 추출했을 때
    ("V-02", "전망치 이전값 1.9%",
     "1.9%",        "올해",
     "0.019",       "2026"),

    # ④ LLM이 변화율을 계산해서 넣었을 때
    ("V-04", "변화율 직접 표기 (-0.4%p)",
     "0.4%p 하락",  "올해",
     "-0.4",        "2026"),

    # ⑤ LLM이 "낮췄다" 방향어를 포함한 경우 — _DECREASE 에 "낮췄" 없음
    ("V-05", "방향어 '낮췄다' 포함",
     "1.5% 낮췄다", "올해",
     "-1.5",        "2026"),   # 기대: -1.5 (감소 방향)

    # ⑥ 시점: "지난 2월" — 전월 패턴과 다름
    ("V-06", "시점 '지난 2월'",
     "1.5%",        "지난 2월",
     "0.015",       "2026-02"),  # 기대: 절대 월 표기

    # ⑦ 시점: "작년 5월"
    ("V-07", "시점 '작년 5월'",
     "1.9%",        "작년 5월",
     "0.019",       "2025-05"),  # 기대: 작년(2025) 5월

    # ⑧ 시점: "올해" 단독
    ("V-08", "시점 '올해'",
     "1.5%",        "올해",
     "0.015",       "2026"),

    # ⑨ 시점: "1998년" — 절대연도 그대로
    ("V-09", "시점 절대연도 1998년",
     "1.5%",        "1998년",
     "0.015",       "1998"),
]


@pytest.mark.asyncio
async def test_normalize_gdp_cases(capsys):
    pass_v = pass_p = total = 0
    rows = []

    for case_id, desc, v_raw, p_raw, v_exp, p_exp in CASES:
        v_got, p_got = await run(v_raw, p_raw)
        v_ok = v_exp is None or v_got == v_exp
        p_ok = p_exp is None or p_got == p_exp
        if v_ok:
            pass_v += 1
        if p_ok:
            pass_p += 1
        total += 1
        rows.append((case_id, desc, v_raw, p_raw, v_got, p_got, v_exp, p_exp, v_ok, p_ok))

    with capsys.disabled():
        print("\n" + "=" * 72)
        print("  normalize_claim - 경제성장률 기사 테스트")
        print("=" * 72)
        for case_id, desc, v_raw, p_raw, v_got, p_got, v_exp, p_exp, v_ok, p_ok in rows:
            vmark = "O" if v_ok else "X"
            pmark = "O" if p_ok else "X"
            print(f"\n{case_id}  {desc}")
            print(f"  value : raw={v_raw!r:30s}  got={v_got!r:10s}  expected={str(v_exp)!r:10s}  [{vmark}]")
            print(f"  period: raw={str(p_raw)!r:30s}  got={p_got!r:10s}  expected={str(p_exp)!r:10s}  [{pmark}]")
        print()
        print("-" * 72)
        print(f"value  PASS {pass_v}/{total}")
        print(f"period PASS {pass_p}/{total}")
        print("=" * 72)

    failures = []
    for case_id, desc, v_raw, p_raw, v_got, p_got, v_exp, p_exp, v_ok, p_ok in rows:
        if not v_ok:
            failures.append(f"{case_id} value  {v_raw!r} → got={v_got!r}  expected={v_exp!r}")
        if not p_ok:
            failures.append(f"{case_id} period {p_raw!r} → got={p_got!r}  expected={p_exp!r}")

    assert not failures, "실패:\n" + "\n".join(failures)
