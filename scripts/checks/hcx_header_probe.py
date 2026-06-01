"""HCX 응답 헤더 프로브 — 테스트앱/서비스앱 식별 단서가 헤더에 있는지 확인.

키는 Infisical 이 주입한 CLOVASTUDIO_API_KEY 를 환경변수에서 읽는다(.env 미사용).
실행:
    uv run x python scripts/checks/hcx_header_probe.py

최소 호출 1건(HCX-DASH-002, maxCompletionTokens=1)만 날린다. 절대 API 키는 출력하지
않으며, 응답(server) 헤더만 덤프한다. rate-limit / app 식별 단서를 강조 출력한다.
"""
from __future__ import annotations

import os
import sys

import httpx

NATIVE_BASE = "https://clovastudio.stream.ntruss.com/v3/chat-completions"
HINT_KEYS = ("rate", "limit", "quota", "qpm", "tpm", "app", "request-id", "x-ncp", "x-clova")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")

    api_key = os.getenv("CLOVASTUDIO_API_KEY")
    if not api_key:
        print(
            "ERROR: CLOVASTUDIO_API_KEY 없음. `uv run x python ...` 로 실행했는지 확인하세요.",
            file=sys.stderr,
        )
        return 1

    model = sys.argv[1] if len(sys.argv) > 1 else "HCX-DASH-002"
    url = f"{NATIVE_BASE}/{model}"
    body = {"messages": [{"role": "user", "content": "hi"}], "maxCompletionTokens": 1}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=30.0)
    except httpx.RequestError as e:
        print(f"[FAIL] 요청 실패: {e}", file=sys.stderr)
        return 2

    print(f"endpoint : {url}")
    print(f"status   : {resp.status_code}")
    print("---- 응답 헤더 (전체) ----")
    for k in sorted(resp.headers):
        print(f"{k}: {resp.headers[k]}")

    print("---- 식별 단서 후보 (rate/limit/app/...) ----")
    hits = {k: v for k, v in resp.headers.items() if any(h in k.lower() for h in HINT_KEYS)}
    if hits:
        for k, v in hits.items():
            print(f"  {k}: {v}")
    else:
        print("  (해당 키워드 헤더 없음)")

    # 본문 result 안에 식별 정보가 있을 수 있어 status/code 만 가볍게 확인
    try:
        data = resp.json()
        status = data.get("status", {})
        print("---- 응답 body status ----")
        print(f"  code={status.get('code')} message={status.get('message')}")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
