"""260615 2~5 gold-figure-recall 테스트의 재실행 (현재 코드, 동일 데이터).

목적: 모듈 개선 후 [5] 값 재현율이 260615 베이스라인 대비 얼마나 올랐나.
  - 데이터/단계/채점 로직은 benchmark/run_2to5_gold_eval.py 를 그대로 import(동일성 보장).
  - 시점 base 는 [1] load_article 더미 2025-04 로 옛 실행과 동일 → 변화분은 순수 모듈 개선.
  - 옛 베이스라인 파일은 보존, 출력은 이 폴더 신규 파일로.

실행:  uv run x python benchmark/260617_2~5_gold-figure-recall_leeaain/260617_2~5_gold-figure-recall_leeaain.py [--concurrency K]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root → benchmark/src import
from benchmark.run_2to5_gold_eval import DATA, _read, _run_all, _summary  # noqa: E402

HERE = Path(__file__).resolve().parent
OUTJSON = HERE / "260617_2~5_gold-figure-recall_leeaain_result.json"
OUTMD = HERE / "260617_2~5_gold-figure-recall_leeaain_report.md"

# 260615 베이스라인 (tests/results/260615_2-5_gold-figure-recall_leeaain.json) — 비교 기준.
OLD = {
    "records_with_evidence": 46, "total_claims_extracted": 248, "total_evidences": 159,
    "gold_absolute": 70, "gold_delta_unwired": 156, "gold_range_or_none_excluded": 10,
    "abs_value_recall": 0.1571, "abs_value_period_recall": 0.0571,
    "abs_value_hits": 11, "abs_value_period_hits": 4, "delta_value_hits": 0,
}


def _delta(new: float, old: float) -> str:
    d = new - old
    sign = "+" if d >= 0 else ""
    return f"{sign}{d * 100:.1f}%p"


def render_md(s: dict) -> str:
    rec = s["records"]
    we = s["records_with_evidence"]
    total = s["gold_absolute"] + s["gold_delta_unwired"] + s["gold_range_or_none_excluded"]
    L = ["# 260617_2~5_gold-figure-recall_leeaain", ""]
    L += ["## 1. 개요",
          "260615 베이스라인과 **동일 데이터·동일 단계([1]~[5])** 를 현재(개선된) 코드로 재실행.",
          f"- 소스: `{DATA.name}` (123건, 전부 label=True)",
          "- 채점 대상: [5] fetch_kosis_data 가 가져온 값이 gold figure(원래 통계표 수치)를 재현하는가.",
          "- 시점 base: [1] load_article 더미 `2025-04` (옛 실행과 동일) → 변화분은 순수 모듈 개선.", ""]
    L += ["## 2. Gold 분류 분포",
          "| gold 분류 | 개수 |", "|---|---|",
          f"| 절대값형 (채점 대상) | {s['gold_absolute']} |",
          f"| 증감형 (미배선, 참고) | {s['gold_delta_unwired']} |",
          f"| 범위/항목없음 (제외) | {s['gold_range_or_none_excluded']} |",
          f"| 합계 | {total} |", ""]
    L += ["## 3. 입력·증거 확보 현황",
          "| 구분 | 값 | 260615 |", "|---|---|---|",
          f"| 입력 레코드 (성공/실패) | {rec} ({s['ok']} / {s['fail']}) | 123 (123 / 0) |",
          f"| evidence 확보 레코드 ([5]) | {we} / {rec} ({we / rec:.1%}) | {OLD['records_with_evidence']} / 123 (37.4%) |",
          f"| 추출 claim / 확보 evidence | {s['total_claims_extracted']} / {s['total_evidences']} | "
          f"{OLD['total_claims_extracted']} / {OLD['total_evidences']} |", ""]
    L += ["## 4. 성능 지표  (★ = 주지표)",
          "| 성능 지표 | 분자/분모 | 재현율 | 260615 | Δ |", "|---|---|---|---|---|",
          f"| 절대값 재현 (값+시점) ★ | {s['abs_value_period_hits']} / {s['gold_absolute']} | "
          f"**{s['abs_value_period_recall']:.3f}** | {OLD['abs_value_period_recall']:.3f} | "
          f"{_delta(s['abs_value_period_recall'], OLD['abs_value_period_recall'])} |",
          f"| 절대값 재현 (값만, ±max(0.5,1%)) | {s['abs_value_hits']} / {s['gold_absolute']} | "
          f"{s['abs_value_recall']:.3f} | {OLD['abs_value_recall']:.3f} | "
          f"{_delta(s['abs_value_recall'], OLD['abs_value_recall'])} |",
          f"| 증감형 적중 (참고) | {s['delta_value_hits']} / {s['gold_delta_unwired']} | "
          f"{s['delta_value_hits'] / s['gold_delta_unwired']:.3f} | 0.000 | — |", ""]
    old_eff = OLD["abs_value_period_recall"]
    L += [f"## 5. 실효 재현율: {s['abs_value_period_recall']:.1%}  "
          f"(260615 {old_eff:.1%} → {s['abs_value_period_recall']:.1%}, {_delta(s['abs_value_period_recall'], old_eff)})",
          "", "## 6. 한계 / 범위 (260615와 동일)",
          "- gold tbl_id 없음 → [4] 표 recall 직접 채점 불가(값 일치로 간접).",
          "- 증감형 gold(전년동월비 등)는 [5] 절대조회로 재현 불가 → 별도 집계, 주지표 제외.",
          "- 범위·비교형 gold(period 'A~B'/다중값)는 단일셀 대조 불가라 제외.",
          "- label 전부 True → 가짜 탐지(7~9) 범위 밖."]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=6)
    args = ap.parse_args()

    rows = _read(DATA, 0)
    print(f"260615 재실행 — {len(rows)}건, 동시 {args.concurrency}\n")
    items = asyncio.run(_run_all(rows, args.concurrency))
    summary = _summary(items)

    OUTJSON.write_text(json.dumps(
        {"source": str(DATA), "stages": "1-5(채점=5)", "rerun_of": "260615_2-5_gold-figure-recall_leeaain",
         "old_baseline": OLD, "summary": summary, "records": items},
        ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    OUTMD.write_text(render_md(summary), encoding="utf-8")

    print(f"\n{json.dumps(summary, ensure_ascii=False)}")
    print(f"저장:\n  {OUTJSON}\n  {OUTMD}")


if __name__ == "__main__":
    main()
