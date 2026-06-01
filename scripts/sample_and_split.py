"""3-4단계 — Stratified 100개 추출 + 4셋 disjoint 분할.

입력: data/processed/candidates_prelabeled.csv
출력:
- data/golden/common_set.csv    (A. 공통, 20개)
- data/golden/baseline_set.csv  (B1. 초기, 10개)
- data/golden/module_set.csv    (B2. 중간, 20개)
- data/golden/final_set.csv     (B3. 최종, 50개)

추출 기준:
- claim_type 5종 (absolute / change_rate / ratio / distribution / comparison) 각 20개씩
- 각 claim_type 안에서 difficulty 분포 easy 40% / medium 40% / hard 20%
- 부족하면 가능한 만큼 + warning

분할: 100개를 무작위 셔플 후 순차 분할 (A 20 / B1 10 / B2 20 / B3 50). disjoint 보장.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# Windows cp949 콘솔에서 한글/특수문자 출력 안정화
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
INPUT_FILE = PROJECT_DIR / "data" / "processed" / "candidates_prelabeled.csv"
OUTPUT_DIR = PROJECT_DIR / "data" / "golden"

RANDOM_SEED = 42
TARGET_TOTAL = 100
CLAIM_TYPES = ["absolute", "change_rate", "ratio", "distribution", "comparison"]
PER_CLAIM_TYPE = TARGET_TOTAL // len(CLAIM_TYPES)  # 20
DIFFICULTY_DISTRIBUTION = {"easy": 0.40, "medium": 0.40, "hard": 0.20}
SPLIT_PLAN = [
    ("common_set", 20),
    ("baseline_set", 10),
    ("module_set", 20),
    ("final_set", 50),
]


def stratified_sample(df: pd.DataFrame) -> pd.DataFrame:
    """claim_type 별 균형 + difficulty 비율 분포로 100개 추출."""
    sampled_parts = []
    warnings = []

    for claim_type in CLAIM_TYPES:
        pool = df[df["claim_type"] == claim_type]
        if len(pool) == 0:
            warnings.append(f"  {claim_type}: 풀에 0개 — 스킵")
            continue

        for difficulty, ratio in DIFFICULTY_DISTRIBUTION.items():
            n_target = round(PER_CLAIM_TYPE * ratio)
            sub_pool = pool[pool["difficulty"] == difficulty]
            n_available = len(sub_pool)

            if n_available >= n_target:
                picked = sub_pool.sample(n=n_target, random_state=RANDOM_SEED)
            else:
                picked = sub_pool
                warnings.append(
                    f"  {claim_type}/{difficulty}: 목표 {n_target}, 보유 {n_available} — "
                    f"가능한 만큼만 (-{n_target - n_available})"
                )
            sampled_parts.append(picked)

    sampled = pd.concat(sampled_parts, ignore_index=True)

    if warnings:
        print("[Warning] 일부 (claim_type, difficulty) 조합 부족:")
        for w in warnings:
            print(w)

    return sampled


def split_into_sets(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """무작위 셔플 후 4셋에 순차 분할 (disjoint)."""
    shuffled = df.sample(frac=1, random_state=RANDOM_SEED).reset_index(drop=True)
    result = {}
    start = 0
    for set_name, size in SPLIT_PLAN:
        end = start + size
        result[set_name] = shuffled.iloc[start:end].copy()
        start = end
    if start < len(shuffled):
        print(f"[Note] 남은 행 {len(shuffled) - start}개 — 분할 계획 초과분, 사용 안 함")
    return result


def print_set_summary(name: str, df: pd.DataFrame) -> None:
    print(f"\n  [{name}] {len(df)} 행")
    print(f"    claim_type:   {df['claim_type'].value_counts().to_dict()}")
    print(f"    difficulty:   {df['difficulty'].value_counts().to_dict()}")
    print(f"    category:     {df['category'].value_counts().to_dict()}")


def main() -> None:
    if not INPUT_FILE.exists():
        print(f"입력 없음: {INPUT_FILE}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(INPUT_FILE, encoding="utf-8-sig")
    print(f"입력: {INPUT_FILE} ({len(df):,} 행)")

    sampled = stratified_sample(df)
    print()
    print(f"--- Stratified 추출: {len(sampled)} / 목표 {TARGET_TOTAL} ---")
    print(f"  claim_type:   {sampled['claim_type'].value_counts().to_dict()}")
    print(f"  difficulty:   {sampled['difficulty'].value_counts().to_dict()}")

    sets = split_into_sets(sampled)

    print()
    print("--- 4셋 disjoint 분할 ---")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for set_name, set_df in sets.items():
        out = OUTPUT_DIR / f"{set_name}.csv"
        set_df.to_csv(out, index=False, encoding="utf-8-sig")
        print_set_summary(set_name, set_df)
        print(f"    저장: {out}")

    # disjoint 검증
    all_indices = pd.concat([s.index.to_series() for s in sets.values()])
    if all_indices.is_unique:
        print("\n[OK] 4셋 disjoint 보장됨 (중복 0)")
    else:
        print("\n[ERROR] 4셋 사이 중복 발견!")
        sys.exit(1)

    print()
    print("[Note] 휴리스틱 분류 기반이라 라벨 정확도 70~80%. 사람 라벨링 단계에서 확정.")


if __name__ == "__main__":
    main()
