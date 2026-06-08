"""단일 구조화(JSON schema) 호출 테스트.

대상 모듈: src.llm.llm_caller
작성자: leeaain2027 <leeaain2027@gmail.com>
작성일: 2026-05-21
"""
from src.llm.llm_caller import LlmCaller

llm_caller = LlmCaller()


# 구조화된 응답이 필요하다면 아래 스키마로 정의합니다.
schema = {
    "type": "object",
    "properties": {
        "년도": {"type": "string"},
        "나이": {"type": "integer"},
        "이름": {"type": "string"},
    },
    "required": ["년도", "나이", "이름"],
    "additionalProperties": False,
}


"""
사용할 수 있는 모델은 provider.py의 PROVIDERS 딕셔너리를 참고하세요.
model_alias는 LLM을 제공하는 업체의 별칭입니다. (예: "openai", "hyperclova", "claude", "gemini")
model_name은 해당 업체에서 사용할 모델의 이름입니다. (예: "gpt-4o", "gpt-3.5-turbo", "claude-opus-4
"""


# 첫번째 질문
response = llm_caller.chat(
    model_alias="openai",
    model_name="gpt-4o",
    messages=[{"role": "user", "content": "지금 미국 대통령은 누구지?"}],
    json_mode=True,
    json_structure=schema,
    max_tokens=4096,
)
print(response.text)
print(response.total_tokens, response.latency_s)


print("-" * 100)


# 두번째 질문
response = llm_caller.chat(
    model_alias="openai",
    model_name="gpt-4o",
    messages=[{"role": "user", "content": "지금 미국 대통령은 누구지?"}],
    max_tokens=4096,
)
print(response.text)
print(response.total_tokens, response.latency_s)
