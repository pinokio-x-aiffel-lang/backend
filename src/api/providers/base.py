"""ChatProvider 인터페이스.

stream 은 이번 PoC 스코프에서 제외(기존 동기 ChatClient 에 stream 메서드가
없고 수정 금지). 필요 시 어댑터에 메서드 1개만 추가하면 된다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.llm import ChatResponse


class ChatProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """1턴/멀티턴 채팅. 기존 ChatResponse 를 그대로 돌려준다."""
        ...
