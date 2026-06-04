"""2단계 prelabel — 후보 풀에 ClaimType / 난이도 / 분야 자동 태깅.

입력: data/processed/candidates.csv
출력: data/processed/candidates_prelabeled.csv

각 기사를 HCX-DASH-002 로 분류:
- claim_type: absolute / change_rate / ratio / distribution / comparison / metaphoric
- difficulty: easy / medium / hard
- category: 인구 / 경제 / 산업 / 사회 / 복지 / 교육 / 기타
- has_verifiable_number: bool
- reason: 한 줄 근거

진행 50개마다 중간 저장 (인터럽트 안전).
실패한 기사는 claim_type="ERROR" 로 표시.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

# src/ import 위해 프로젝트 루트를 sys.path 에 추가
sys.path.insert(0, str(PROJECT_DIR))

from src.llm import ChatClient, LlmError  # noqa: E402  (sys.path 조작 후 import)
INPUT_FILE = PROJECT_DIR / "data" / "processed" / "candidates.csv"
OUTPUT_FILE = PROJECT_DIR / "data" / "processed" / "candidates_prelabeled.csv"

COL_TITLE = "기사제목"
COL_BODY = "기사 본문 전체"
MAX_BODY_CHARS = 2000  # 토큰 비용 절감용
SAVE_EVERY = 50

SYSTEM_PROMPT = """너는 한국 뉴스의 수치 주장을 분류하는 보조 도우미다. 출력은 반드시 JSON 한 개로만 한다."""

USER_PROMPT_TEMPLATE = """다음 기사를 분류해줘.

[제목]
{title}

[본문 (앞 {max_chars}자)]
{body}

[JSON 스키마]
{{
  "claim_type": "absolute | change_rate | ratio | distribution | comparison | metaphoric",
  "difficulty": "easy | medium | hard",
  "category": "인구 | 경제 | 산업 | 사회 | 복지 | 교육 | 기타",
  "has_verifiable_number": true | false,
  "reason": "한 줄 근거"
}}

[분류 기준]
- claim_type: 기사의 핵심 수치 주장이 어떤 형태인가
  - absolute: 절대값 (예: "출생아 23만 명")
  - change_rate: 변화율 (예: "전년 대비 5% 감소")
  - ratio: 비율/비중 (예: "20대의 30%")
  - distribution: 순위/분포 (예: "1위 ~ 5위")
  - comparison: 두 대상 비교 (예: "A 가 B 보다 많다")
  - metaphoric: 정성적·비유적 표현 (예: "역대 최대", 정량 X)
- difficulty: 통계청 데이터로 검증할 때의 난이도
  - easy: 절대값 + 명확한 시점 + 명시된 출처
  - medium: 비율/변화율 + 모집단 명시, 통계청 매핑 어렵지 않음
  - hard: 단위 환산 필요 / 모집단 모호 / 추정값 / 비교 시점 모호
- category: 통계 분야
- has_verifiable_number: 본문에 통계청으로 매핑 가능한 수치 1개 이상 있나
- reason: 위 분류의 한 줄 근거 (40자 이내)

다른 텍스트 없이 위 JSON 만 출력."""


def build_messages(title: str, body: str) -> list[dict]:
    body_truncated = body[:MAX_BODY_CHARS]
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_PROMPT_TEMPLATE.format(
                title=title,
                body=body_truncated,
                max_chars=MAX_BODY_CHARS,
            ),
        },
    ]


def parse_label(text: str) -> dict:
    """LLM 응답 텍스트 → dict. 파싱 실패 시 예외 발생."""
    return json.loads(text)


def main() -> None:
    if not INPUT_FILE.exists():
        print(f"입력 파일 없음: {INPUT_FILE}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(INPUT_FILE, encoding="utf-8-sig")
    total = len(df)
    print(f"입력: {INPUT_FILE} ({total:,} 행)")

    client = ChatClient(default_model="HCX-DASH-002")
    print("ChatClient 초기화 OK (HCX-DASH-002, json_mode)")

    # 결과 컬럼 초기화
    for col in ["claim_type", "difficulty", "category", "has_verifiable_number", "reason"]:
        if col not in df.columns:
            df[col] = ""

    success = 0
    error = 0
    total_tokens = 0
    start_s = time.time()

    for i, row in df.iterrows():
        # 이미 라벨링된 행은 스킵 (재실행 시 이어가기)
        if isinstance(row["claim_type"], str) and row["claim_type"] not in ("", "nan"):
            success += 1
            continue

        title = str(row.get(COL_TITLE, ""))
        body = str(row.get(COL_BODY, ""))

        try:
            response = client.fetch_chat(
                messages=build_messages(title, body),
                temperature=0.1,
                max_tokens=400,
                json_mode=True,
            )
            label = parse_label(response.text)
            df.at[i, "claim_type"] = label.get("claim_type", "")
            df.at[i, "difficulty"] = label.get("difficulty", "")
            df.at[i, "category"] = label.get("category", "")
            df.at[i, "has_verifiable_number"] = label.get("has_verifiable_number", False)
            df.at[i, "reason"] = label.get("reason", "")
            total_tokens += response.total_tokens
            success += 1
        except LlmError as e:
            print(f"[{i+1}/{total}] LlmError: {e}", file=sys.stderr)
            df.at[i, "claim_type"] = "ERROR"
            df.at[i, "reason"] = f"LlmError: {str(e)[:80]}"
            error += 1
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[{i+1}/{total}] JSON 파싱 실패: {e}", file=sys.stderr)
            df.at[i, "claim_type"] = "ERROR"
            df.at[i, "reason"] = f"파싱 실패: {str(e)[:80]}"
            error += 1

        # 진행 상황
        if (i + 1) % 10 == 0:
            elapsed = time.time() - start_s
            rate = (i + 1) / elapsed
            eta_s = (total - i - 1) / rate if rate > 0 else 0
            print(
                f"  [{i+1:>4}/{total}] "
                f"성공 {success:>4} / 실패 {error:>3} | "
                f"토큰 {total_tokens:>7,} | "
                f"속도 {rate:.2f}/s | "
                f"ETA {eta_s/60:.1f}분"
            )

        # 중간 저장 (인터럽트 안전)
        if (i + 1) % SAVE_EVERY == 0:
            df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    # 최종 저장
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    elapsed = time.time() - start_s

    print()
    print("--- prelabel 완료 ---")
    print(f"  전체:        {total:,}")
    print(f"  성공:        {success:,}")
    print(f"  실패:        {error:,}")
    print(f"  총 토큰:      {total_tokens:,}")
    print(f"  소요 시간:    {elapsed/60:.1f}분")
    print(f"  저장:        {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
