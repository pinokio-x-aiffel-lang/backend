"""기사 본문 샘플로 normalize_claim 수동 검증.

아래 기사에서 LLM 이 추출할 법한 value_raw / period_raw 를 직접 구성한다.
그 입력으로 normalize_claim 의 실제 출력을 확인한다.

테스트 기사:
  통계청에 따르면 지난달 한국 근로자의 주당 평균 근로시간은 38.8시간이다.
  일본의 65세 이상 노동시장 참여율(26%)이 프랑스(4%)를 앞서고 있으며,
  일본의 1997년 이후 연평균 노동생산성 증가율(1.1%)이 서유럽(0.8%)을 앞섰다.
  25~64세는 주당 평균 30시간을 일하지만, 65세 이상은 7시간 일하는 것으로 집계됐다.

실행:
  uv run pytest tests/test_normalize_article_sample.py -s -v
"""
from __future__ import annotations

import asyncio

import pytest

from src.modules.normalize_claim import _normalize_period, _parse_value

# ── 기사 발행일 (테스트 기준일) ───────────────────────────────────────────────
BASE = "2026-06-08"

# ── (case_id, 설명, value_raw, period_raw, expected_value, expected_period) ───
#
# expected 가 None 이면 "어떤 값이든 raw 와 달라야 한다" (정규화 확인만)
# expected_period 가 None 이면 period 정규화 검증 생략

CASES = [
    (
        "C-01",
        "주당 평균 근로시간 (plain float)",
        "38.8", "지난달",
        "38.8", "2026-05",         # 지난달 → 2026-06의 전월
    ),
    (
        "C-02",
        "일본 65세 이상 참여율 (퍼센트)",
        "26%", "현재",
        "0.26", None,
    ),
    (
        "C-03",
        "프랑스 참여율 (퍼센트)",
        "4%", "현재",
        "0.04", None,
    ),
    (
        "C-04",
        "일본 노동생산성 증가율 (소수 퍼센트)",
        "1.1%", "1997년 이후",
        "0.011", "1997",            # "이후" 어미가 잘려도 연도는 정상
    ),
    (
        "C-05",
        "서유럽 노동생산성 증가율 (소수 퍼센트)",
        "0.8%", "1997년 이후",
        "0.008", "1997",
    ),
    (
        "C-06",
        "25~64세 주당 근로시간 (숫자+단위)",
        "30시간", "현재",
        "30", None,
    ),
    (
        "C-07",
        "65세 이상 주당 근로시간 (숫자+단위)",
        "7시간", "현재",
        "7", None,
    ),
    # ── 추가: LLM이 다르게 추출할 수 있는 변형 ────────────────────────────────
    (
        "C-08",
        "단위 붙은 근로시간 (38.8시간 통째로 추출될 경우)",
        "38.8시간", "지난달",
        "38.8", "2026-05",
    ),
    (
        "C-09",
        "26 (단위 없이 숫자만)",
        "26", None,
        "26", None,
    ),
    (
        "C-10",
        "전년대비 증가율 방향어 포함 추출",
        "1.1% 증가", "1997년 이후",
        "+1.1", "1997",
    ),
]


async def _run(value_raw: str, period_raw: str | None):
    value_out = await _parse_value(value_raw)
    period_out = _normalize_period(period_raw, BASE) if period_raw else ""
    return value_out, period_out


def _fmt(case_id, desc, v_raw, p_raw, v_got, p_got, v_exp, p_exp):
    v_ok = "O" if v_got == v_exp else "X"
    p_ok = "O" if (p_exp is None or p_got == p_exp) else "X"
    return (
        f"\n{case_id}  {desc}\n"
        f"  value : raw={v_raw!r:20s}  got={v_got!r:12s}  expected={v_exp!r:10s}  [{v_ok}]\n"
        f"  period: raw={str(p_raw)!r:20s}  got={p_got!r:12s}  expected={str(p_exp)!r:10s}  [{p_ok}]"
    )


@pytest.mark.asyncio
async def test_all_article_cases(capsys):
    results = []
    pass_v = pass_p = total = 0

    for case_id, desc, v_raw, p_raw, v_exp, p_exp in CASES:
        v_got, p_got = await _run(v_raw, p_raw)
        v_ok = v_got == v_exp
        p_ok = p_exp is None or p_got == p_exp

        results.append((case_id, desc, v_raw, p_raw, v_got, p_got, v_exp, p_exp, v_ok, p_ok))
        if v_ok:
            pass_v += 1
        if p_ok:
            pass_p += 1
        total += 1

    # 결과 출력 (-s 옵션으로 볼 수 있음)
    with capsys.disabled():
        print("\n" + "=" * 70)
        print("  normalize_claim  기사 샘플 테스트 결과")
        print("=" * 70)
        for case_id, desc, v_raw, p_raw, v_got, p_got, v_exp, p_exp, v_ok, p_ok in results:
            print(_fmt(case_id, desc, v_raw, p_raw, v_got, p_got, v_exp, p_exp))
        print("-" * 70)
        print(f"value  PASS: {pass_v}/{total}")
        print(f"period PASS: {pass_p}/{total}  (expected=None 케이스는 자동 PASS)")
        print("=" * 70)

    # pytest 판정: 모든 케이스 통과 여부
    failures = [
        f"{r[0]} value  {r[2]!r} → got {r[4]!r}, expected {r[6]!r}"
        for r in results if not r[8]
    ] + [
        f"{r[0]} period {r[3]!r} → got {r[5]!r}, expected {r[7]!r}"
        for r in results if not r[9]
    ]
    assert not failures, "실패 케이스:\n" + "\n".join(failures)
