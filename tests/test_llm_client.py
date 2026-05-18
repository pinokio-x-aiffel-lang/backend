"""ChatClient 단위 테스트.

실제 NCP API 호출 없이 SDK 를 mock 으로 대체해서 클라이언트 로직만 검증.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from openai import APIError

from src.llm import ChatClient, ChatResponse, LlmError


def _build_fake_sdk_response(
    content: str = "추출된 Claim...",
    total_tokens: int = 1247,
    prompt_tokens: int = 980,
    completion_tokens: int = 267,
    model: str = "HCX-005",
    finish_reason: str = "stop",
) -> MagicMock:
    """SDK 의 chat.completions.create() 반환 객체를 흉내내는 가짜 응답."""
    fake = MagicMock()
    fake.choices = [MagicMock()]
    fake.choices[0].message.content = content
    fake.choices[0].finish_reason = finish_reason
    fake.usage.total_tokens = total_tokens
    fake.usage.prompt_tokens = prompt_tokens
    fake.usage.completion_tokens = completion_tokens
    fake.model = model
    fake.model_dump.return_value = {"id": "fake", "model": model}
    return fake


def test_정상_호출_시_ChatResponse_필드_모두_채워진다():
    """가짜 SDK 응답에서 8개 필드가 올바르게 ChatResponse 로 옮겨지는지."""
    client = ChatClient(api_key="test_key", default_model="HCX-005")
    fake_response = _build_fake_sdk_response()

    with patch.object(client._sdk.chat.completions, "create", return_value=fake_response):
        result = client.fetch_chat(messages=[{"role": "user", "content": "안녕"}])

    assert isinstance(result, ChatResponse)
    assert result.text == "추출된 Claim..."
    assert result.total_tokens == 1247
    assert result.prompt_tokens == 980
    assert result.completion_tokens == 267
    assert result.model == "HCX-005"
    assert result.finish_reason == "stop"
    assert result.latency_s >= 0
    assert result.raw == {"id": "fake", "model": "HCX-005"}


def test_default_model_이_있으면_fetch_chat_시_자동_적용된다():
    """ChatClient(default_model="HCX-005") + model 인자 생략 → SDK 호출에 HCX-005 전달."""
    client = ChatClient(api_key="test_key", default_model="HCX-005")
    fake_response = _build_fake_sdk_response()

    with patch.object(client._sdk.chat.completions, "create", return_value=fake_response) as mock_create:
        client.fetch_chat(messages=[{"role": "user", "content": "안녕"}])

    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["model"] == "HCX-005"


def test_model_과_default_model_둘_다_없으면_ValueError():
    """model 인자도 default_model 도 None 이면 ValueError. SDK 호출 X."""
    client = ChatClient(api_key="test_key")  # default_model 미설정

    with pytest.raises(ValueError, match="model"):
        client.fetch_chat(messages=[{"role": "user", "content": "안녕"}])


def test_json_mode_True_면_response_format_이_SDK_에_전달된다():
    """json_mode=True → SDK kwargs 에 response_format={'type': 'json_object'} 포함."""
    client = ChatClient(api_key="test_key", default_model="HCX-005")
    fake_response = _build_fake_sdk_response()

    with patch.object(client._sdk.chat.completions, "create", return_value=fake_response) as mock_create:
        client.fetch_chat(messages=[{"role": "user", "content": "안녕"}], json_mode=True)

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["response_format"] == {"type": "json_object"}


def test_APIError_가_LlmError_로_wrap_되고_원본은_cause_로_보존된다():
    """SDK 의 APIError 발생 → LlmError 로 wrap. __cause__ 로 원본 추적 가능."""
    client = ChatClient(api_key="test_key", default_model="HCX-005")
    original = APIError("rate limit hit", request=MagicMock(), body=None)

    with patch.object(client._sdk.chat.completions, "create", side_effect=original):
        with pytest.raises(LlmError) as exc_info:
            client.fetch_chat(messages=[{"role": "user", "content": "안녕"}])

    assert exc_info.value.__cause__ is original


def test_api_key_없으면_생성자에서_LlmError():
    """환경변수도 .env 도 없으면 ChatClient() 생성 시 즉시 LlmError."""
    with patch("src.llm.client.load_dotenv"), patch.dict("os.environ", {}, clear=True):
        with pytest.raises(LlmError, match="HCX_API_KEY"):
            ChatClient()


def test_fetch_chat_의_timeout_이_SDK_호출에_override_로_전달된다():
    """ChatClient(timeout=60) 인스턴스에서 fetch_chat(timeout=120) → SDK 에 120 전달."""
    client = ChatClient(api_key="test_key", default_model="HCX-005", timeout=60.0)
    fake_response = _build_fake_sdk_response()

    with patch.object(client._sdk.chat.completions, "create", return_value=fake_response) as mock_create:
        client.fetch_chat(messages=[{"role": "user", "content": "안녕"}], timeout=120.0)

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["timeout"] == 120.0


def test_생략된_옵션_인자는_SDK_kwargs_에_안_들어간다():
    """temperature/max_tokens/timeout 생략 시 SDK 호출 kwargs 에 키 자체가 없음."""
    client = ChatClient(api_key="test_key", default_model="HCX-005")
    fake_response = _build_fake_sdk_response()

    with patch.object(client._sdk.chat.completions, "create", return_value=fake_response) as mock_create:
        client.fetch_chat(messages=[{"role": "user", "content": "안녕"}])

    call_kwargs = mock_create.call_args.kwargs
    assert "temperature" not in call_kwargs
    assert "max_tokens" not in call_kwargs
    assert "response_format" not in call_kwargs  # json_mode=False 이므로
    assert "timeout" not in call_kwargs
