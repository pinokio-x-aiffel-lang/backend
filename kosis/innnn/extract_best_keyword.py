"""HCX-005 로 KOSIS 검색 API(searchNm)에 그대로 넣을 BEST 키워드를 추출한다.

배경:
    KOSIS `statisticsList.do?method=getList` 의 searchNm 파라미터는
    통계표명(TBL_NM)에 대한 부분 문자열 매칭이다. 자연어 질의를 그대로
    넣으면 매칭이 깨지는 경우가 많아, 통계표명에 실제 등장할 만한 핵심
    명사구로 정제할 필요가 있다.

실행:
    infisical run -- uv run python kosis/innnn/extract_best_keyword.py

키 출처:
    Infisical CLI 가 주입한 CLOVASTUDIO_API_KEY 를 LlmCaller 가 환경변수에서
    읽는다. .env 는 사용하지 않는다(프로젝트 정책).
"""
from __future__ import annotations

import os
import sys

from src.llm.llm_caller import LlmCaller


SYSTEM_PROMPT = """당신은 KOSIS(국가통계포털) 통계표 검색용 키워드 추출기다.
사용자가 찾고자 하는 통계 주제로부터, KOSIS 검색 API의 searchNm 파라미터에
그대로 넣을 BEST 키워드 1개만 출력한다.

KOSIS 검색은 통계표명(TBL_NM)에 대한 부분 문자열 매칭이다. 따라서:

1. 통계표 명칭에 실제로 등장할 핵심 명사구만 남긴다.
2. 연도(예: 2023, 2020년)는 키워드에서 제외한다. 시점은 표명에 들어가지
   않고, KOSIS 데이터 조회 시 startPrdDe/endPrdDe 로 따로 거른다.
3. 지역 한정어(전국, 서울 등)는 통계표의 분류 차원(OBJ_VAR)에 들어가는
   경우가 많고 표명에는 잘 들어가지 않는다. 가능하면 제외한다.
4. 자연어에서 띄어 쓴 합성어는 표명에서 붙어 있는 경우가 흔하다
   (예: "소비자 물가 지수" → "소비자물가지수"). 자연스러우면 공백을 제거한다.
5. 가능한 한 짧고 식별력 있는 명사구 1개로 한정한다.

출력 형식: 키워드 1개의 문자열만. 따옴표, 마침표, 설명, 줄바꿈, 라벨 없이
키워드 그 자체만 출력한다."""


QUERIES: list[str] = [
    "전국 소비자 물가 지수",
    "축산농가",
    "2023 소비자 물가 등락률",
]


def extract_keyword(llm: LlmCaller, query: str) -> tuple[str, int, float]:
    """HCX-005 1회 호출로 BEST 키워드를 뽑는다.

    Returns:
        (keyword, total_tokens, latency_s)
    """
    resp = llm.chat(
        model_alias="hyperclova",
        model_name="HCX-005",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        max_tokens=64,
        temperature=0.0,
    )
    # 모델이 따옴표/공백/마침표를 섞어 출력하는 경우가 잦아 가볍게 정리한다.
    keyword = resp.text.strip().strip("\"'`").rstrip(".").strip()
    return keyword, resp.total_tokens, resp.latency_s


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    if not os.getenv("CLOVASTUDIO_API_KEY"):
        print(
            "ERROR: CLOVASTUDIO_API_KEY 없음. "
            "`infisical run -- uv run python ...` 로 실행했는지 확인하세요.",
            file=sys.stderr,
        )
        return 1

    llm = LlmCaller()

    print("=" * 72)
    print("HCX-005 BEST 키워드 추출 결과")
    print("=" * 72)
    for q in QUERIES:
        kw, tokens, latency = extract_keyword(llm, q)
        print()
        print(f"[원본 질의] {q}")
        print(f"[BEST 키워드] {kw}")
        print(f"  (tokens={tokens}, latency={latency:.2f}s)")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
