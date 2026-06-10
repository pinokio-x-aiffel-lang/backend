"""Langfuse 트레이싱 동작 확인 테스트.

실행:
    uv run x 260527_x_langfuse-aain_leeaain.py

대상 모듈: src.observability.traced_chat
작성자: leeaain2027 <leeaain2027@gmail.com>
작성일: 2026-05-27
"""

from src.observability import traced_chat


def main() -> None:
    messages = [{"role": "user", "content": "안녕! 한 문장으로 짧게 자기소개 해줘."}]

    print("LLM 호출 중...")
    resp = traced_chat(
        model_alias="gemini",
        model_name="gemini-2.5-flash",
        messages=messages,
        max_tokens=128,
        trace_name="langfuse-test",
    )

    print(f"응답: {resp.text}")
    print(f"토큰: input={resp.prompt_tokens}, output={resp.completion_tokens}, total={resp.total_tokens}")
    print(f"지연: {resp.latency_s:.2f}s")
    print("Langfuse 트레이싱 완료 — 대시보드에서 'langfuse-test' trace 확인.")

if __name__ == "__main__":
    main()
