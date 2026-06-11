"""3단계 normalize_claim 기간 정규화 — 케이스 매트릭스 전수 테스트.

절대/상대(연·월·분기·반기)/연말연초/경계(base 1월·연도만·무base)/복합 표현 64케이스를
_normalize_period(룰)과 _resolve_period(룰→LLM 폴백)에 넣어 gold와 비교한다.

    uv run x python tests/260612_3_normalize-period_leeaain.py

대상 모듈: src.modules.normalize_claim (_normalize_period / _resolve_period)
작성자: leeaain2027  작성일: 2026-06-12
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.modules.normalize_claim import _normalize_period, _resolve_period

OUT_DIR = Path("tests/results")
BASE_NAME = "260612_3_normalize-period_leeaain_02"  # _01 = R1·R2 수정 후, _02 = R3·R4 수정 후
A = "2025-04"   # 기본 base(기사 작성일)

# (category, raw, base, gold)  — gold=None: 정의상 해소 불가(월 미상 등)가 정답
CASES = [
    # 절대 표기
    ("절대", "2024년 3월", A, "2024-03"),
    ("절대", "2024년 12월", A, "2024-12"),
    ("절대", "2023년 1분기", A, "2023-Q1"),
    ("절대", "2023년 4분기", A, "2023-Q4"),
    ("절대", "2024년 상반기", A, "2024-H1"),
    ("절대", "2024년 하반기", A, "2024-H2"),
    ("절대", "2024년", A, "2024"),
    ("절대", "2024", A, "2024"),
    ("절대", "2020년 이후", A, "2020"),
    ("절대", "2019년부터", A, "2019"),
    ("절대", "2024년 말", A, "2024-12"),
    ("절대", "2024년 초", A, "2024-01"),
    # 절대 표기 + base 없음 (절대값은 base 불필요해야 정상)
    ("절대·무base", "2024년 3월", "", "2024-03"),
    ("절대·무base", "2024년 말", "", "2024-12"),
    ("절대·무base", "2024년 초", "", "2024-01"),
    # 상대 — 연
    ("상대·연", "작년", A, "2024"),
    ("상대·연", "전년", A, "2024"),
    ("상대·연", "지난해", A, "2024"),
    ("상대·연", "올해", A, "2025"),
    ("상대·연", "금년", A, "2025"),
    ("상대·연", "재작년", A, "2023"),
    ("상대·연", "내년", A, "2026"),
    ("상대·연", "1년 전", A, "2024"),
    ("상대·연", "5년 전", A, "2020"),
    ("상대·연", "1년 후", A, "2026"),
    # 상대 — 월
    ("상대·월", "지난달", A, "2025-03"),
    ("상대·월", "전월", A, "2025-03"),
    ("상대·월", "이달", A, "2025-04"),
    ("상대·월", "이번 달", A, "2025-04"),
    ("상대·월", "지난 3월", A, "2025-03"),
    ("상대·월", "지난 2월", A, "2025-02"),
    ("상대·월", "작년 3월", A, "2024-03"),
    ("상대·월", "지난해 12월", A, "2024-12"),
    ("상대·월", "전년 동월", A, "2024-04"),
    ("상대·월", "3개월 전", A, "2025-01"),
    ("상대·월", "6개월 전", A, "2024-10"),
    ("상대·월", "4월", A, "2025-04"),
    ("상대·월", "올해 5월", A, "2025-05"),
    # 상대 — 분기
    ("상대·분기", "전분기", A, "2025-Q1"),
    ("상대·분기", "이번 분기", A, "2025-Q2"),
    ("상대·분기", "전년 동기", A, "2024-Q2"),
    ("상대·분기", "올 1분기", A, "2025-Q1"),
    ("상대·분기", "1분기", A, "2025-Q1"),
    ("상대·분기", "지난 1분기", A, "2025-Q1"),
    ("상대·분기", "작년 4분기", A, "2024-Q4"),
    # 상대 — 반기
    ("상대·반기", "상반기", A, "2025-H1"),
    ("상대·반기", "하반기", A, "2025-H2"),
    ("상대·반기", "이번 반기", A, "2025-H1"),
    ("상대·반기", "전반기", A, "2024-H2"),
    ("상대·반기", "지난해 상반기", A, "2024-H1"),
    # 연말·연초
    ("연말연초", "작년 말", A, "2024-12"),
    ("연말연초", "연말", A, "2025-12"),
    ("연말연초", "연초", A, "2025-01"),
    ("연말연초", "작년 초", A, "2024-01"),
    ("연말연초", "지난달 말", A, "2025-03"),
    # 경계 — base 변형
    ("경계", "전월", "2025-01", "2024-12"),
    ("경계", "전분기", "2025-01", "2024-Q4"),
    ("경계", "전년 동월", "2025-01", "2024-01"),
    ("경계", "전반기", "2025-09", "2025-H1"),
    ("경계", "이번 반기", "2025-09", "2025-H2"),
    ("경계", "이번 분기", "2025-07", "2025-Q3"),
    ("경계", "지난달", "2025", None),     # base에 월 없음 → 해소 불가가 정답
    ("경계", "지난달", "", None),         # base 없음 → 해소 불가가 정답
    # 일 단위 (포맷 밖 — 현행 출력형식은 Y/M/Q/H만)
    ("일단위", "지난 3일", A, None),
]


async def run_case(cat: str, raw: str, base: str, gold: str | None) -> dict:
    rule = _normalize_period(raw, base)
    if rule is not None:
        final, path = rule, "rule"
    else:
        final = await _resolve_period(raw, base)
        path = "llm" if final != raw else "miss(raw반환)"
    if gold is None:
        ok = final in (raw, None)  # 해소 불가가 정답 → raw 반환(미해소)이 정상
    else:
        ok = final == gold
    return {"category": cat, "raw": raw, "base": base, "gold": gold,
            "rule": rule, "final": final, "path": path, "ok": ok}


async def main() -> None:
    results = [await run_case(*c) for c in CASES]

    n = len(results)
    n_ok = sum(r["ok"] for r in results)
    rule_hit = sum(1 for r in results if r["rule"] is not None)
    rule_ok = sum(1 for r in results if r["rule"] is not None and r["ok"])
    cats: dict[str, list] = {}
    for r in results:
        cats.setdefault(r["category"], []).append(r)

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / f"{BASE_NAME}.json").write_text(json.dumps({
        "module": "normalize_claim (_normalize_period/_resolve_period)",
        "n": n, "ok": n_ok,
        "rule_coverage": round(rule_hit / n, 4),
        "rule_accuracy_when_hit": round(rule_ok / rule_hit, 4) if rule_hit else 0,
        "results": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    def row(r):
        mark = "✓" if r["ok"] else "✗"
        gold = r["gold"] if r["gold"] is not None else "(해소불가)"
        return (f"| {r['raw']} | {r['base'] or '—'} | {gold} | "
                f"{r['final']} | {r['path']} | {mark} |")

    cat_lines = []
    for cat, rs in cats.items():
        ok = sum(r["ok"] for r in rs)
        cat_lines.append(f"| {cat} | {ok}/{len(rs)} |")

    fails = [r for r in results if not r["ok"]]
    head = "| raw | base | gold | 결과 | 경로 | 판정 |\n|--|--|--|--|--|--|"
    md = f"""# 3단계 normalize_claim — 기간 정규화 케이스 매트릭스

| 항목 | 내용 |
|---|---|
| ① 목적 | 기간(period) 정규화가 절대·상대·경계·복합 표현 전반에서 정확한지 |
| ② 검증 대상 모듈 | `src.modules.normalize_claim` (`_normalize_period`/`_resolve_period`) |
| ③ 도구로만 쓰인 모듈 | `src.llm` (LLM 폴백 경로 — HCX, `NORMALIZE_PERIOD` preset) |
| ④ 일자/작성자 | 2026-06-12 / leeaain2027 |

- 케이스 {n}개 (gold 수작업), 기본 base=2025-04. gold "(해소불가)" = base 미상 등으로 해소 불가가 정답.
- 경로: rule=룰베이스 적중, llm=룰 실패→LLM 폴백 채택, miss=폴백도 실패(raw 반환)
- 원자료: `{BASE_NAME}.json`

## 요약

| 전체 정확도 | 룰 커버리지 | 룰 적중 시 정확도 |
|---|---|---|
| **{n_ok}/{n} ({n_ok/n:.1%})** | {rule_hit}/{n} ({rule_hit/n:.1%}) | {rule_ok}/{rule_hit} ({rule_ok/rule_hit:.1%}) |

**카테고리별**

| 카테고리 | 정답 |
|---|--|
{chr(10).join(cat_lines)}

## 오답 ({len(fails)}건)

{head}
{chr(10).join(row(r) for r in fails) if fails else '_없음_'}

## 전체 케이스

{head}
{chr(10).join(row(r) for r in results)}
"""
    (OUT_DIR / f"{BASE_NAME}.md").write_text(md, encoding="utf-8")

    print(f"전체 {n_ok}/{n}  룰 커버리지 {rule_hit}/{n}  룰 정확도 {rule_ok}/{rule_hit}")
    for cat, rs in cats.items():
        print(f"  {cat}: {sum(r['ok'] for r in rs)}/{len(rs)}")
    print("오답:")
    for r in fails:
        print(f"  ✗ [{r['category']}] {r['raw']} (base={r['base']or'—'}) gold={r['gold']} got={r['final']} ({r['path']})")
    print(f"저장: {OUT_DIR}/{BASE_NAME}.{{md,json}}")


if __name__ == "__main__":
    asyncio.run(main())
