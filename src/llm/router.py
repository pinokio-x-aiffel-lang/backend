from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

from src.llm.client import ChatClient, ChatResponse, LlmError
from src.llm.provider import MODELS, PROVIDERS


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise LlmError(f"환경변수 {name} 를 찾을 수 없습니다.")
    return value


class LlmRouter:
    """model_alias를 받아 적절한 provider/model로 라우팅."""

    def __init__(self) -> None:
        load_dotenv()

    @lru_cache(maxsize=16)
    def _get_client(self, provider_name: str) -> ChatClient:
        if provider_name not in PROVIDERS:
            raise LlmError(f"등록되지 않은 provider: {provider_name}")

        provider = PROVIDERS[provider_name]

        api_key = _get_required_env(provider.api_key_env)

        base_url = None
        if provider.base_url_env is not None:
            base_url = _get_required_env(provider.base_url_env)

        return ChatClient(
            api_key=api_key,
            base_url=base_url,
        )

    def chat(
        self,
        model_alias: str,
        model_name: str,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        timeout: float | None = None,
    ) -> ChatResponse:
        if model_alias not in MODELS:
            raise LlmError(f"등록되지 않은 model_alias: {model_alias}")

        model_config = MODELS[model_alias]

        if json_mode and not model_config.supports_json_object:
            raise LlmError(
                f"{model_alias} 모델은 json_object 모드를 지원하지 않도록 설정되어 있습니다."
            )

        client = self._get_client(model_config.provider)

        return client.fetch_chat(
            messages=messages,
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            timeout=timeout,
        )
