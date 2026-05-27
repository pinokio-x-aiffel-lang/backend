"""실제 HCX-005 호출이 Langfuse 에 자동 기록되는지 보여주는 데모.

traced_chat 으로 키워드 추출 3건을 호출하면, 각 호출이 Langfuse generation
(입력 messages / 출력 text / 모델 / 토큰 / 지연)으로 대시보드에 남는다.

실행:
    infisical run --env dev --path /LangFuse -- uv run python infra/langfuse/demo_hcx_trace.py
"""
from __future__ import annotations

import sys

from langfuse import get_client, observe

from src.observability import traced_chat

sys.stdout.reconfigure(encoding="utf-8")

SYSTEM_PROMPT = (
    "당신은 KOSIS 통계표 검색용 키워드 추출기다. 사용자 질의에서 검색 API에 넣을 "
    "BEST 키워드 1개만 출력한다. 연도·지역 한정어는 제외하고, 공백은 자연스러우면 "
    "제거한다. 키워드 문자열만 출력한다."
)

QUERIES = [
    "전국 소비자 물가 지수",
    "축산농가",
    "2023 소비자 물가 등락률",
]


@observe(name="hcx-keyword-extraction-demo")
def run_demo() -> None:
    """전체 데모를 하나의 트레이스로 묶고, 각 HCX 호출을 그 안의 generation 으로 남긴다."""
    for q in QUERIES:
        resp = traced_chat(
            model_alias="hyperclova",
            model_name="HCX-005",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": q},
            ],
            trace_name="hcx-keyword",
            max_tokens=64,
            temperature=0.0,
        )
        kw = resp.text.strip().strip("\"'`").rstrip(".").strip()
        print(f"  '{q}' → '{kw}'  (tokens={resp.total_tokens}, {resp.latency_s:.2f}s)")


def main() -> int:
    lf = get_client()
    if not lf.auth_check():
        print("Langfuse 인증 실패 — 자격/HOST 확인 (infisical run 으로 실행했는지)", file=sys.stderr)
        return 1

    print("HCX-005 키워드 추출 (traced) —")
    run_demo()
    lf.flush()
    print("✅ 완료 — Langfuse 대시보드 Tracing 탭에서 'hcx-keyword-extraction-demo' 확인")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
