"""2단계 prelabel (휴리스틱 버전) — 정규식 기반으로 ClaimType / 난이도 / 분야 자동 분류.

LLM 없이 정규식 패턴 매칭으로 대략 분류. 정확도 70~80% 수준이지만 stratified
sampling 의 균형 잡기에는 충분. **사람 라벨링 단계에서 정확한 분류 확정**.

입력: data/processed/candidates.csv
출력: data/processed/candidates_prelabeled.csv
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

# Windows cp949 콘솔에서 한글/특수문자 출력 안정화
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
INPUT_FILE = PROJECT_DIR / "data" / "processed" / "candidates.csv"
OUTPUT_FILE = PROJECT_DIR / "data" / "processed" / "candidates_prelabeled.csv"

COL_BODY = "기사 본문 전체"

# claim_type 패턴 — 우선순위 순서로 첫 매치 적용
CLAIM_TYPE_PATTERNS = [
    ("comparison", re.compile(r"보다\s*[가-힣]*(?:많|적|높|낮|크|작|빠|느)|에\s*비해|와\s*비교|대비\s*[가-힣]*(?:많|적|높|낮)")),
    ("change_rate", re.compile(r"\d+(?:\.\d+)?\s*%[^가-힣]*(?:증가|감소|상승|하락|줄|늘|올|내려|확대|축소)|전년\s*대비|지난해\s*대비|전월\s*대비|전기\s*대비")),
    ("distribution", re.compile(r"\d+\s*위|상위\s*\d+|하위\s*\d+|순위|랭킹|\d+\s*등")),
    ("ratio", re.compile(r"\d+(?:\.\d+)?\s*%|비중|비율|차지하|점유")),
    ("absolute", re.compile(r"\d+(?:,\d{3})*\s*(?:명|원|건|개|곳|만|억|조)")),
]

# difficulty 패턴
TIME_REGEX = re.compile(r"\d{4}\s*년|\d+\s*분기|\d+\s*월")
STAT_SOURCE_REGEX = re.compile(r"통계청|국가통계|국가데이터처|KOSIS|통계포털")
ESTIMATION_REGEX = re.compile(r"전망|추정|예상|예측|예정|관측")

# category 키워드
CATEGORY_KEYWORDS = {
    "인구": ["출생", "사망", "혼인", "이혼", "인구", "고령", "노인", "청년", "세대", "결혼"],
    "경제": ["GDP", "경제성장", "성장률", "환율", "금리", "물가", "소비자물가", "CPI", "PPI", "통화"],
    "산업": ["산업", "기업", "제조", "수출", "수입", "매출", "기업체", "공장", "생산"],
    "고용": ["고용", "실업", "취업", "일자리", "구직", "임금", "근로"],
    "사회": ["범죄", "사건", "사고", "안전", "주택", "주거", "교통", "환경", "오염"],
    "복지": ["복지", "연금", "기초", "돌봄", "취약", "기초생활", "수급"],
    "교육": ["교육", "학생", "학교", "대학", "입학", "졸업", "사교육"],
}


def classify_claim_type(text: str) -> str:
    """본문에서 가장 먼저 매칭되는 claim_type 반환. 매칭 없으면 'absolute' fallback."""
    if not isinstance(text, str):
        return "absolute"
    for label, regex in CLAIM_TYPE_PATTERNS:
        if regex.search(text):
            return label
    return "absolute"  # 1차 필터 통과한 거라 수치는 있을 것 — 절대값 fallback


def classify_difficulty(text: str) -> str:
    """본문에서 난이도 추정."""
    if not isinstance(text, str):
        return "medium"
    has_stat_source = bool(STAT_SOURCE_REGEX.search(text))
    has_time = bool(TIME_REGEX.search(text))
    has_estimation = bool(ESTIMATION_REGEX.search(text))

    if has_estimation:
        return "hard"  # 추정/전망은 검증 어려움
    if has_stat_source and has_time:
        return "easy"
    return "medium"


def classify_category(text: str) -> str:
    """본문에서 가장 많이 매칭되는 카테고리 반환. 매칭 없으면 '기타'."""
    if not isinstance(text, str):
        return "기타"
    counts = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        counts[cat] = sum(1 for kw in keywords if kw in text)
    best = max(counts.items(), key=lambda x: x[1])
    return best[0] if best[1] > 0 else "기타"


def main() -> None:
    if not INPUT_FILE.exists():
        print(f"입력 파일 없음: {INPUT_FILE}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(INPUT_FILE, encoding="utf-8-sig")
    print(f"입력: {INPUT_FILE} ({len(df):,} 행)")

    bodies = df[COL_BODY].fillna("")
    df["claim_type"] = bodies.apply(classify_claim_type)
    df["difficulty"] = bodies.apply(classify_difficulty)
    df["category"] = bodies.apply(classify_category)
    df["source_method"] = "heuristic"  # 나중에 LLM prelabel 로 보강 시 구분용

    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    print()
    print("--- 휴리스틱 분류 결과 ---")
    print()
    print("[claim_type 분포]")
    print(df["claim_type"].value_counts().to_string())
    print()
    print("[difficulty 분포]")
    print(df["difficulty"].value_counts().to_string())
    print()
    print("[category 분포]")
    print(df["category"].value_counts().to_string())
    print()
    print(f"저장: {OUTPUT_FILE}")
    print()
    print("[Note] 정확도 70~80% 수준 (정규식 기반). 사람 라벨링 단계에서 정확한 분류 확정 필요.")


if __name__ == "__main__":
    main()
