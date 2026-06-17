"""3단계 정규화 룰 점검 — 기사 자연어 수치 표현 리스트를 슬롯별로 파싱.

value 슬롯은 _parse_value, period_value 슬롯은 _normalize_period(base 의존).
LLM 미사용(순수 룰). 각 표현의 기대(검증대상/미검증대상)를 명시해 PASS/FAIL 채점한다.

- SKIP: 의도적으로 룰이 다루면 안 되는 표현(코로나 이전·올 들어·최근·사상 최대·두 자릿수·
  거의 절반 + bare-only로 결정한 '두 배로'). → 기대 None.
- KNOWN_WRONG: 값은 나오지만 silent-wrong(추후 보강 후보). 커버리지는 통과로 보되 ⚠ 표시.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.modules.normalize_claim import _normalize_period, _parse_value

# 발행일 기준(상대 시점 해소용) — 스키마 예시 chosun_20250314 와 동일.
BASE = "2025-03-14"

# 의도적 미검증(룰 비대상) — 기대 결과 = None. docs/numeral_parser_coverage.md §3·§4.
SKIP = {
    "코로나 이전", "올 들어", "최근", "사상 최대", "두 자릿수 성장", "거의 절반",
    "두 배로",  # bare-only 결정 → 조사 결합형은 미커버
}

# 값은 나오지만 틀림(silent-wrong) — 커버리지 통과지만 값 오류 표시.
KNOWN_WRONG = {
    "7:3", "4명 중 1명", "3명에 1명꼴", "수십만", "수백억", "십수 명",
    "두 배 이상", "1위", "상위 10%", "톱5", "절반으로 줄어",
}

# (슬롯, 표현, 카테고리)
CASES: list[tuple[str, str, str]] = [
    # ── value: 절대 수치 + 단위 ──
    ("value", "3.1%", "절대+단위"),
    ("value", "49퍼센트", "절대+단위"),
    ("value", "1,250원", "절대+단위"),
    ("value", "2290억원", "절대+단위"),
    ("value", "21만6000명", "절대+단위"),
    ("value", "350만 가구", "절대+단위"),
    ("value", "1조 2천억", "절대+단위"),
    ("value", "5천4백만", "절대+단위"),
    ("value", "0.7%포인트", "절대+단위"),
    # ── value: 증감 ──
    ("value", "5.2% 증가", "증감"),
    ("value", "3%p 하락", "증감"),
    ("value", "21만6000명 증가", "증감"),
    ("value", "2290억원 줄었다", "증감"),
    ("value", "2배", "증감"),
    ("value", "3.5배", "증감"),
    ("value", "갑절", "증감"),
    ("value", "두 배", "증감"),
    ("value", "세 배", "증감"),
    ("value", "급증", "증감"),
    ("value", "두 배로", "증감"),
    ("value", "절반으로 줄어", "증감"),
    # ── value: 비율·분수 ──
    ("value", "3대 5", "비율/분수"),
    ("value", "7:3", "비율/분수"),
    ("value", "3분의 1", "비율/분수"),
    ("value", "1/3", "비율/분수"),
    ("value", "2할 5푼", "비율/분수"),
    ("value", "절반", "비율/분수"),
    ("value", "과반", "비율/분수"),
    ("value", "4명 중 1명", "비율/분수"),
    ("value", "3명에 1명꼴", "비율/분수"),
    # ── value: 범위·경계 ──
    ("value", "1850~1950원", "범위/경계"),
    ("value", "100만~200만", "범위/경계"),
    ("value", "30% 이상", "범위/경계"),
    ("value", "50명 미만", "범위/경계"),
    ("value", "최대 3조", "범위/경계"),
    ("value", "최소 100명", "범위/경계"),
    ("value", "5천 명부터 1만 명까지", "범위/경계"),
    # ── value: 근사·모호 ──
    ("value", "약 3만", "근사/모호"),
    ("value", "3만여", "근사/모호"),
    ("value", "3만 안팎", "근사/모호"),
    ("value", "3만 가량", "근사/모호"),
    ("value", "수십만", "근사/모호"),
    ("value", "수백억", "근사/모호"),
    ("value", "십수 명", "근사/모호"),
    ("value", "거의 절반", "근사/모호"),
    ("value", "두 배 이상", "근사/모호"),
    ("value", "두 자릿수 성장", "근사/모호"),
    ("value", "사상 최대", "근사/모호"),
    # ── value: 순위·서수 ──
    ("value", "1위", "순위/서수"),
    ("value", "상위 10%", "순위/서수"),
    ("value", "톱5", "순위/서수"),
    # ── period_value: 절대 ──
    ("period_value", "2025년 3월", "기간-절대"),
    ("period_value", "2025/03", "기간-절대"),
    ("period_value", "2025.03", "기간-절대"),
    ("period_value", "2025년 1분기", "기간-절대"),
    ("period_value", "2025년 상반기", "기간-절대"),
    ("period_value", "2025년 하반기", "기간-절대"),
    ("period_value", "2024년", "기간-절대"),
    ("period_value", "2024년 이후", "기간-절대"),
    ("period_value", "2024 회계연도", "기간-절대"),
    # ── period_value: 상대(base 의존) ──
    ("period_value", "작년 3월", "기간-상대"),
    ("period_value", "전년 동월", "기간-상대"),
    ("period_value", "재작년", "기간-상대"),
    ("period_value", "지난달", "기간-상대"),
    ("period_value", "전분기", "기간-상대"),
    ("period_value", "올해 3월", "기간-상대"),
    ("period_value", "이번 1분기", "기간-상대"),
    # ── period_value: 미검증 대상 + 갭 ──
    ("period_value", "최근", "기간-미커버"),
    ("period_value", "올 들어", "기간-미커버"),
    ("period_value", "2020~2024년", "기간-미커버"),
    ("period_value", "코로나 이전", "기간-미커버"),
]


def run_case(slot: str, expr: str) -> str | None:
    if slot == "value":
        return _parse_value(expr)
    return _normalize_period(expr, BASE)


def judge(expr: str, result: str | None) -> tuple[str, bool, str]:
    """(expect, passed, status) — expect=skip|cover."""
    if expr in SKIP:
        expect = "skip"
        if result is None:
            return expect, True, "✅ 미검증(의도대로)"
        return expect, False, "❌ 검증됨(미검증이어야)"
    expect = "cover"
    if result is None:
        return expect, False, "❌ 미스(갭)"
    if expr in KNOWN_WRONG:
        return expect, True, "⚠ 검증됨(값 오류)"
    return expect, True, "✅ 검증됨"


def main() -> None:
    rows = []
    for slot, expr, category in CASES:
        out = run_case(slot, expr)
        expect, passed, status = judge(expr, out)
        rows.append(
            {
                "slot": slot,
                "category": category,
                "expr": expr,
                "result": out,
                "expect": expect,
                "passed": passed,
                "status": status,
            }
        )

    out_path = Path(__file__).with_name(Path(__file__).stem + "_result.json")
    out_path.write_text(
        json.dumps(
            {"base": BASE, "n": len(rows), "rows": rows},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"base={BASE}  n={len(rows)}")
    print("slot\texpect\tcategory\texpr\tresult\tstatus")
    for r in rows:
        res = "None" if r["result"] is None else r["result"]
        print(
            f"{r['slot']}\t{r['expect']}\t{r['category']}\t{r['expr']}\t{res}\t{r['status']}"
        )

    n = len(rows)
    skip_rows = [r for r in rows if r["expect"] == "skip"]
    skip_ok = sum(1 for r in skip_rows if r["passed"])
    cover_rows = [r for r in rows if r["expect"] == "cover"]
    cover_hit = sum(1 for r in cover_rows if r["result"] is not None)
    cover_wrong = sum(1 for r in cover_rows if r["expr"] in KNOWN_WRONG)
    gaps = [r["expr"] for r in cover_rows if r["result"] is None]
    print(
        f"\n[검증대상 cover] hit {cover_hit}/{len(cover_rows)} "
        f"(그중 값오류 {cover_wrong}, 미스갭 {len(gaps)}: {gaps})"
    )
    print(f"[미검증대상 skip] None 확인 {skip_ok}/{len(skip_rows)}  "
          f"→ {[r['expr'] for r in skip_rows]}")


if __name__ == "__main__":
    main()
