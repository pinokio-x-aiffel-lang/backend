"""Langfuse 연결 확인용 첫 트레이스 전송.

환경변수에서 자격을 읽는다 (코드에 키를 박지 않음):
    LANGFUSE_PUBLIC_KEY   pk-lf-...
    LANGFUSE_SECRET_KEY   sk-lf-...
    LANGFUSE_HOST         http://localhost:3000

실행 (PowerShell):
    $env:LANGFUSE_PUBLIC_KEY="pk-lf-..."
    $env:LANGFUSE_SECRET_KEY="sk-lf-..."
    $env:LANGFUSE_HOST="http://localhost:3000"
    uv run python infra/langfuse/test_trace.py
"""
from __future__ import annotations

import sys

from langfuse import get_client, observe

sys.stdout.reconfigure(encoding="utf-8")


@observe(name="langfuse-setup-test")
def setup_check(message: str) -> str:
    """이 함수 호출 자체가 하나의 트레이스로 기록된다 (입력/출력 자동 캡처)."""
    return f"첫 트레이스 전송 성공 🎉 (입력: {message})"


def main() -> int:
    lf = get_client()  # LANGFUSE_PUBLIC_KEY / SECRET_KEY / HOST 환경변수 사용

    if not lf.auth_check():
        print(
            "인증 실패 — LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST 확인",
            file=sys.stderr,
        )
        return 1

    setup_check("Langfuse 연결 테스트")

    lf.flush()  # 종료 전 버퍼 전송 보장
    print("✅ 트레이스 전송 완료 — Langfuse UI에서 확인하세요 (Tracing 탭)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
