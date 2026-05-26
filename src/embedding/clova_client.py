"""CLOVA Studio 임베딩 클라이언트.

`src/llm/client.py` 의 ChatClient 와 같은 철학을 따른다 — 클라이언트는 순수하다.

하지 않음:
- .env 로딩 (키는 호출자가 주입한다. 운영 시 Infisical CLI 가 주입한
  CLOVASTUDIO_API_KEY 를 호출자가 읽어 넘긴다.)
- provider 선택 / model alias 해석
- 재시도 (단, 배치 헬퍼는 호출 간 sleep 만 둔다)
- 벡터 저장 / 유사도 계산

인증은 fetch_hcx_native 와 동일하게 `Authorization: Bearer {api_key}` 헤더.

엔드포인트 경로는 계정·발급 방식에 따라 다르다(testapp 유무, appId 유무).
그래서 host/model/app_id 로 URL 을 조립하되, 전체 URL 을 직접 넘기는 것도
허용한다. 정확한 경로·차원은 CLOVA Studio 콘솔 문서로 한 번 확인할 것.
검색(질의↔문서 비대칭 매칭) 용도이므로 기본 모델은 clir-emb-dolphin.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_HOST = "https://clovastudio.stream.ntruss.com"
DEFAULT_MODEL = "clir-emb-dolphin"  # 검색/CLIR 용 (질의↔문서). STS 가 아님.
DEFAULT_TIMEOUT_S = 30.0


class EmbeddingError(Exception):
    """임베딩 호출 실패 시 던지는 공통 예외. 원본은 __cause__ 로 보존."""


@dataclass
class EmbeddingResponse:
    """임베딩 1건 응답 컨테이너."""

    vector: list[float]
    input_tokens: int
    model: str
    latency_s: float
    raw: dict


class ClovaEmbeddingClient:
    def __init__(
        self,
        api_key: str,
        *,
        host: str = DEFAULT_HOST,
        model: str = DEFAULT_MODEL,
        app_id: str | None = None,
        endpoint: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        """
        Parameters
        ----------
        api_key : str
            CLOVASTUDIO_API_KEY. 호출자가 주입한다(여기서 .env 를 읽지 않음).
        host, model, app_id :
            엔드포인트 URL 조립 재료. app_id 가 있으면 경로 끝에 붙는다.
        endpoint : str | None
            지정하면 host/model/app_id 조립을 무시하고 이 URL 을 그대로 쓴다.
        """
        if not api_key:
            raise ValueError("api_key 가 비어 있습니다. CLOVASTUDIO_API_KEY 를 주입하세요.")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.endpoint = endpoint or self._build_endpoint(host, model, app_id)
        self._client = httpx.Client(timeout=timeout)

    @staticmethod
    def _build_endpoint(host: str, model: str, app_id: str | None) -> str:
        # 예: {host}/testapp/v1/api-tools/embedding/clir-emb-dolphin/{appId}
        # 신규 nv- 키 체계에선 /testapp, appId 가 생략될 수 있다 — 콘솔 문서 확인.
        base = f"{host.rstrip('/')}/testapp/v1/api-tools/embedding/{model}"
        return f"{base}/{app_id}" if app_id else base

    def embed(self, text: str) -> EmbeddingResponse:
        """텍스트 1건을 임베딩한다. 실패 시 EmbeddingError."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {"text": text}

        start_s = time.time()
        try:
            resp = self._client.post(self.endpoint, json=body, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise EmbeddingError(
                f"임베딩 호출 실패: {e.response.status_code} {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise EmbeddingError(f"임베딩 호출 실패: {e}") from e
        latency_s = time.time() - start_s

        data: dict[str, Any] = resp.json()
        result = data.get("result", {})
        vector = result.get("embedding")
        if not isinstance(vector, list):
            raise EmbeddingError(f"응답에 embedding 벡터가 없습니다: {data}")
        return EmbeddingResponse(
            vector=vector,
            input_tokens=result.get("inputTokens", 0),
            model=self.model,
            latency_s=latency_s,
            raw=data,
        )

    def embed_batch(
        self,
        texts: list[str],
        *,
        sleep_between: float = 0.1,
    ) -> list[EmbeddingResponse]:
        """여러 텍스트를 순차 임베딩한다(CLOVA 는 요청당 1텍스트).

        오프라인 카탈로그 임베딩용. 레이트리밋 회피를 위해 호출 간 sleep.
        실패는 즉시 전파한다(부분 결과 캐싱은 호출자 책임).
        """
        out: list[EmbeddingResponse] = []
        for i, t in enumerate(texts):
            out.append(self.embed(t))
            if sleep_between and i < len(texts) - 1:
                time.sleep(sleep_between)
        return out
