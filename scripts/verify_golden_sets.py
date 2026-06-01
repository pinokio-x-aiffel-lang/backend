"""4셋 검증 — 초기 설계 기준과 실제 결과 비교.

검증 항목:
1. 각 셋 크기 (목표 vs 실제)
2. 난이도 분포 (easy 40 / medium 40 / hard 20)
3. ClaimType 균형 (5종 각 20)
4. 검색 레이블 True/False 균형 (50:50)
5. 분야 다양성
6. 본문 길이 분포
7. 4셋 disjoint
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
GOLDEN_DIR = PROJECT_DIR / "data" / "golden"

EXPECTED_SIZES = {
    "common_set": 20,
    "baseline_set": 10,
    "module_set": 20,
    "final_set": 50,
}
EXPECTED_DIFFICULTY = {"easy": 0.40, "medium": 0.40, "hard": 0.20}
EXPECTED_CLAIM_TYPES = ["absolute", "change_rate", "ratio", "distribution", "comparison"]


def percent_str(n: int, total: int) -> str:
    return f"{n} ({n / total * 100:.0f}%)" if total > 0 else f"{n} (0%)"


def verify_one_set(name: str, df: pd.DataFrame) -> dict:
    n = len(df)
    expected_n = EXPECTED_SIZES[name]
    result = {
        "size_ok": n == expected_n,
        "n": n,
        "expected": expected_n,
    }
    print(f"\n=== {name} (실제 {n} / 목표 {expected_n}) ===")
    if n != expected_n:
        print(f"  ⚠️  크기 차이: {n - expected_n}")

    # 난이도 분포
    diff_counts = df["difficulty"].value_counts().to_dict()
    print(f"  [난이도]")
    for diff in ["easy", "medium", "hard"]:
        count = diff_counts.get(diff, 0)
        target_pct = EXPECTED_DIFFICULTY[diff] * 100
        actual_pct = count / n * 100 if n > 0 else 0
        flag = "OK" if abs(actual_pct - target_pct) < 15 else "NG"
        print(f"    {diff:6} {count:>3} ({actual_pct:>4.0f}%) — 목표 {target_pct:.0f}%  [{flag}]")

    # ClaimType 분포
    ct_counts = df["claim_type"].value_counts().to_dict()
    print(f"  [ClaimType]")
    for ct in EXPECTED_CLAIM_TYPES:
        count = ct_counts.get(ct, 0)
        target = expected_n // len(EXPECTED_CLAIM_TYPES)
        print(f"    {ct:14} {count:>3}  — 목표 {target}")

    # 카테고리 (분야)
    cat_counts = df["category"].value_counts().to_dict()
    print(f"  [Category]    {cat_counts}")

    # 검색 레이블
    if "검색 구분 레이블" in df.columns:
        label_counts = df["검색 구분 레이블"].value_counts().to_dict()
        print(f"  [검색레이블]   {label_counts}")
        result["label_distribution"] = label_counts

    # 본문 길이
    if "본문_길이" in df.columns:
        avg = df["본문_길이"].mean()
        short = (df["본문_길이"] < 800).sum()
        mid = ((df["본문_길이"] >= 800) & (df["본문_길이"] < 2000)).sum()
        long_ = (df["본문_길이"] >= 2000).sum()
        print(f"  [본문길이]    평균 {avg:.0f}자 / 짧음(<800) {short}, 중간 {mid}, 김(>=2000) {long_}")

    return result


def main() -> None:
    print("=" * 70)
    print("4셋 골드 데이터셋 검증 — 초기 설계 vs 실제")
    print("=" * 70)

    all_indices = []
    summary_rows = []

    for name in EXPECTED_SIZES:
        path = GOLDEN_DIR / f"{name}.csv"
        if not path.exists():
            print(f"\n[ERROR] {path} 없음")
            sys.exit(1)
        df = pd.read_csv(path, encoding="utf-8-sig")
        # 기사 URL 또는 행 인덱스로 disjoint 확인
        if "URL" in df.columns:
            all_indices.extend(df["URL"].tolist())
        verify_one_set(name, df)
        summary_rows.append({"name": name, "size": len(df), "expected": EXPECTED_SIZES[name]})

    # disjoint 검증
    print("\n" + "=" * 70)
    print("Disjoint 검증")
    print("=" * 70)
    unique_urls = len(set(all_indices))
    total_urls = len(all_indices)
    if unique_urls == total_urls:
        print(f"  [OK] 4셋 disjoint 보장 (URL 기준 {total_urls}개 모두 unique)")
    else:
        print(f"  [NG] 중복 발견: {total_urls - unique_urls}개")

    # 종합
    print("\n" + "=" * 70)
    print("종합 — 초기 설계 vs 실제")
    print("=" * 70)
    total_actual = sum(r["size"] for r in summary_rows)
    total_expected = sum(r["expected"] for r in summary_rows)
    print(f"  총 개수: {total_actual} / {total_expected} (차이 {total_actual - total_expected})")
    for r in summary_rows:
        flag = "OK" if r["size"] == r["expected"] else "NG"
        print(f"    {r['name']:14} {r['size']:>3} / {r['expected']:>3}  [{flag}]")


if __name__ == "__main__":
    main()
