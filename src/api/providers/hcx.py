"""HyperCLOVA X 어댑터.

기존 src/llm/client.py 의 ChatClient 를 그대로 위임 호출한다. 재작성하지
않는다. ChatClient 는 동기이므로 스레드풀로 오프로딩해 이벤트 루프를 막지
않는다.

키 출처: Infisical CLI 가 주입한 CLOVASTUDIO_API_KEY 를 config 에서 읽어
ChatClient(api_key=...) 로 명시 전달한다. (client.py 는 HCX_API_KEY 를 읽지만
수정 금지라 여기서 이름 차이를 흡수.)
"""
from __future__ import annotations

from anyio import to_thread

from src.api.providers.base import ChatProvider
from src.llm import ChatClient, ChatResponse


class HcxProvider(ChatProvider):
    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        self._model = model
        self._client = ChatClient(
            api_key=api_key,
            default_model=model,
            timeout=timeout,
        )

    async def chat(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        return await to_thread.run_sync(
            lambda: self._client.fetch_chat(
                messages=messages,
                model=self._model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )
