from __future__ import annotations

import os

from dotenv import load_dotenv

from src.llm.client import ChatClient, ChatResponse, LlmError, fetch_hcx_native
from src.llm.provider import (
    GPT_MAX_COMPLETION_TOKENS_MODELS,
    GPT_RESPONSES_MODELS,
    HCX_NATIVE_MODELS,
    PROVIDERS,
    ProviderConfig,
)


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise LlmError(f"환경변수 {name} 를 찾을 수 없습니다.")
    return value


class LlmCaller:
    """model_alias를 받아 적절한 provider/model로 LLM을 호출."""

    def __init__(self) -> None:
        load_dotenv()
        self._clients: dict[str, ChatClient] = {}

    def _get_client(self, model_alias: str, provider: ProviderConfig) -> ChatClient:
        if model_alias not in self._clients:
            api_key = _get_required_env(provider.api_key_env)
            self._clients[model_alias] = ChatClient(api_key=api_key, base_url=provider.base_url)
        return self._clients[model_alias]

    def chat(
        self,
        model_alias: str,
        model_name: str,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        json_structure: dict | None = None,
        timeout: float | None = None,
    ) -> ChatResponse:
        if model_alias not in PROVIDERS:
            raise LlmError(f"등록되지 않은 provider: {model_alias}")

        provider = PROVIDERS[model_alias]

        if json_mode and not provider.supports_json_object:
            raise LlmError(
                f"[{model_name}] provider는 json_object 모드를 지원하지 않습니다."
            )

        if model_alias == "hyperclova" and model_name.lower() in HCX_NATIVE_MODELS:
            if provider.native_url is None:
                raise LlmError("native_url이 설정되지 않았습니다.")
            api_key = _get_required_env(provider.api_key_env)
            return fetch_hcx_native(
                api_key=api_key,
                url=provider.native_url,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                json_structure=json_structure,
                timeout=timeout or 60.0,
            )

        client = self._get_client(model_alias, provider)

        if model_alias == "openai":
            if model_name in GPT_RESPONSES_MODELS:
                return client.fetch_responses(
                    messages=messages,
                    model_name=model_name,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
            return client.fetch_chat(
                messages=messages,
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                use_max_completion_tokens=model_name in GPT_MAX_COMPLETION_TOKENS_MODELS,
                json_mode=json_mode,
                json_structure=json_structure,
                timeout=timeout,
            )

        return client.fetch_chat(
            messages=messages,
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            json_structure=json_structure,
            timeout=timeout,
        )
