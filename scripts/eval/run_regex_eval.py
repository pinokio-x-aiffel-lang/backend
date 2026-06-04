"""실제 기사 데이터 대상 regex normalize 평가.

Usage:
    uv run python scripts/eval/run_regex_eval.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from src.modules.normalize_claim import _parse_value

JSONL = Path("data/eval/labeling_base_success.jsonl")
SKIP = {"불명", ""}  # 판단 불가 sentinel


OUT = Path("data/eval/regex_eval_result.md")


def _categorize(raw: str, gt: str, got: str) -> str:
    """불일치 원인 분류."""
    # 억 10배 오류: GT가 regex의 1/10
    try:
        if float(got) / float(gt) == 10.0:
            return "GT오류:억×10배"
    except (ValueError, ZeroDivisionError):
        pass
    # % 소수 변환 차이
    if "%" in raw and gt.startswith("0."):
        return "포맷:% 소수변환"
    # 방향+수치 규약 차이
    if got.startswith(("+", "-")) and not gt.startswith(("+", "-")):
        return "포맷:방향부호"
    if gt.startswith("-") and not got.startswith("-"):
        return "포맷:방향부호"
    # raw에 괄호 포함
    if "(" in raw or ")" in raw:
        return "엣지:괄호포함"
    # 날짜 범위
    if "부터" in raw or "까지" in raw or "~" in raw:
        return "엣지:날짜범위"
    return "기타"


def main() -> None:
    claims = []
    with JSONL.open(encoding="utf-8") as f:
        for line in f:
            claims.extend(json.loads(line)["claims"])

    rows = [
        (c["value"]["raw"], c["value"]["llm_value"])
        for c in claims
        if c["value"]["raw"] not in SKIP and c["value"]["llm_value"] not in SKIP
    ]

    match = 0
    mismatches: list[tuple[str, str, str, str]] = []

    for raw, gt in rows:
        got = _parse_value(raw)
        if got == gt:
            match += 1
        else:
            cat = _categorize(raw, gt, got)
            mismatches.append((raw, gt, got, cat))

    total = match + len(mismatches)

    # 카테고리 집계
    from collections import Counter
    cat_counts = Counter(m[3] for m in mismatches)

    lines: list[str] = []
    lines.append(f"# regex eval 결과  ({total} claims)\n")
    lines.append(f"- MATCH   : {match} / {total}  ({match/total*100:.1f}%)")
    lines.append(f"- MISMATCH: {len(mismatches)} / {total}  ({len(mismatches)/total*100:.1f}%)\n")

    lines.append("## 불일치 원인 분류\n")
    lines.append(f"| 분류 | 건수 |")
    lines.append(f"|---|---|")
    for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {cat} | {cnt} |")

    lines.append("\n## 불일치 목록 전체\n")
    lines.append(f"| raw | ground truth | regex | 분류 |")
    lines.append(f"|---|---|---|---|")
    for raw, gt, got, cat in mismatches:
        lines.append(f"| {raw} | {gt} | {got} | {cat} |")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"결과 저장: {OUT}")
    print(f"MATCH {match}/{total} ({match/total*100:.1f}%),  MISMATCH {len(mismatches)}")
    print("\n불일치 원인 분류:")
    for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:<20} {cnt:>4}건")


if __name__ == "__main__":
    main()
