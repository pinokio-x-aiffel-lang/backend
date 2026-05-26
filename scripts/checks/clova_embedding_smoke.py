"""CLOVA 임베딩 클라이언트 스모크 — 텍스트 1건 임베딩해 차원/지연 확인.

키는 Infisical 이 주입한 CLOVASTUDIO_API_KEY 를 환경변수에서 읽는다(.env 미사용).
따라서 다음처럼 실행한다:

    infisical run -- uv run python scripts/checks/clova_embedding_smoke.py

엔드포인트 경로가 계정마다 다르므로(app_id/testapp 유무), 필요하면 환경변수로 덮어쓴다:
    CLOVA_EMBEDDING_ENDPOINT=...        # 전체 URL 직접 지정
    CLOVA_EMBEDDING_APP_ID=...          # app_id 만 지정
    CLOVA_EMBEDDING_MODEL=clir-emb-dolphin
"""
from __future__ import annotations

import os
import sys

from src.embedding import ClovaEmbeddingClient, EmbeddingError


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    api_key = os.getenv("CLOVASTUDIO_API_KEY")
    if not api_key:
        print(
            "ERROR: CLOVASTUDIO_API_KEY 없음. "
            "`infisical run -- ...` 로 실행했는지 확인하세요.",
            file=sys.stderr,
        )
        return 1

    client = ClovaEmbeddingClient(
        api_key=api_key,
        model=os.getenv("CLOVA_EMBEDDING_MODEL", "clir-emb-dolphin"),
        app_id=os.getenv("CLOVA_EMBEDDING_APP_ID"),
        endpoint=os.getenv("CLOVA_EMBEDDING_ENDPOINT"),
    )
    print(f"endpoint: {client.endpoint}")

    text = "2024년 1인당 쌀 소비량"
    try:
        res = client.embed(text)
    except EmbeddingError as e:
        print(f"[FAIL] EmbeddingError: {e}", file=sys.stderr)
        return 2

    print(f"text: {text!r}")
    print(f"dim={len(res.vector)} inputTokens={res.input_tokens} latency={res.latency_s:.3f}s")
    print(f"vector[:5]={[round(v, 4) for v in res.vector[:5]]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
