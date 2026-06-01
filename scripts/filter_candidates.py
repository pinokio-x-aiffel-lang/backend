"""1차 필터 — 클라비 2,707개 풀에서 수치 검증 가능성 있는 후보 추출.

입력: ../3_데이터/학습용 데이터 확보/AI 기반 뉴스 사실검증 시스템 프로젝트 데이터.csv
출력: data/processed/candidates.csv (UTF-8)

필터링 기준 (AND):
1. 본문 길이 >= 300자
2. 본문에 수치 표현 (백분율/단위수치/소수) 1개 이상
3. 본문에 시점 표현 (연도/분기/월/지난해 등) 1개 이상

다음 단계: prelabel 스크립트로 ClaimType/난이도/분야 자동 태깅 → stratified sampling 으로 100개 추출.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd


# 경로
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
WORKSPACE_DIR = PROJECT_DIR.parent
DATA_FILE = (
    WORKSPACE_DIR
    / "3_데이터"
    / "학습용 데이터 확보"
    / "AI 기반 뉴스 사실검증 시스템 프로젝트 데이터.csv"
)
OUTPUT_DIR = PROJECT_DIR / "data" / "processed"
OUTPUT_FILE = OUTPUT_DIR / "candidates.csv"

# 컬럼명
COL_BODY = "기사 본문 전체"

# 수치 패턴
NUMBER_PATTERNS = [
    r"\d+(?:,\d{3})*\.?\d*\s*%",                       # 백분율 (12%, 12.5%)
    r"\d+(?:,\d{3})*\s*(?:명|원|건|배|위|개|곳|만|억|조)",  # 단위 수치
    r"\d+\.\d+",                                        # 소수 (3.14)
]
NUMBER_REGEX = re.compile("|".join(NUMBER_PATTERNS))

# 시점 패턴
TIME_PATTERNS = [
    r"\d{4}\s*년",       # 2024년
    r"\d+\s*년대",       # 2000년대
    r"\d+\s*분기",       # 3분기
    r"\d+\s*월",         # 5월
    r"지난해|작년|올해|내년|지난달|이번달",
]
TIME_REGEX = re.compile("|".join(TIME_PATTERNS))

MIN_BODY_LENGTH = 300


def count_matches(text: str, regex: re.Pattern) -> int:
    """본문에서 정규식 매칭 개수 반환."""
    if not isinstance(text, str):
        return 0
    return len(regex.findall(text))


def main() -> None:
    print(f"입력: {DATA_FILE}")
    if not DATA_FILE.exists():
        print(f"파일 없음: {DATA_FILE}", file=sys.stderr)
        sys.exit(1)

    # cp949 인코딩 (한글 깨짐 방지)
    df = pd.read_csv(DATA_FILE, encoding="cp949")
    print(f"로드 완료: {len(df):,} 행, 컬럼 {list(df.columns)}")

    if COL_BODY not in df.columns:
        print(f"'{COL_BODY}' 컬럼 없음", file=sys.stderr)
        sys.exit(1)

    bodies = df[COL_BODY].fillna("")
    df["본문_길이"] = bodies.str.len()
    df["수치_매칭"] = bodies.apply(lambda x: count_matches(x, NUMBER_REGEX))
    df["시점_매칭"] = bodies.apply(lambda x: count_matches(x, TIME_REGEX))

    cond_length = df["본문_길이"] >= MIN_BODY_LENGTH
    cond_number = df["수치_매칭"] >= 1
    cond_time = df["시점_매칭"] >= 1

    filtered = df[cond_length & cond_number & cond_time].copy()
    before, after = len(df), len(filtered)

    print()
    print("--- 필터링 결과 ---")
    print(f"  전체:                  {before:>5,}")
    print(f"  본문 < {MIN_BODY_LENGTH}자 제외:        {(~cond_length).sum():>5,}")
    print(f"  수치 0건 제외:           {(~cond_number).sum():>5,}")
    print(f"  시점 0건 제외:           {(~cond_time).sum():>5,}")
    print(f"  AND 통과:              {after:>5,}")
    print(f"  통과 비율:             {after / before * 100:>5.1f}%")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filtered.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    print()
    print(f"저장: {OUTPUT_FILE}")
    print(f"  ({after:,} 행, UTF-8-sig 인코딩, Excel/메모장에서 한글 정상)")


if __name__ == "__main__":
    main()
