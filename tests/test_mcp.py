from src.llm.llm_caller import LlmCaller
from src.llm.provider import HCX_MODEL_INFO, HCX_MODELS

llm_caller = LlmCaller()


# 구조화된 응답이 필요하다면 아래 스키마로 정의합니다.
SCHEMA = {
    "type": "object",
    "properties": {
        "이름": {"type": "string", "description": "Person's name"},
        "국적": {"type": "string", "description": "Person's nationality"},
    },
    "required": ["이름", "국적"],
    "additionalProperties": False,
}

QUESTION = "MCP에 대한 정의와 뉴스기사 텍스트를 제공할테니 뉴스기사 텍스트를 읽고 MCP를 실행시켜서 결과를 받아서 출력하세요. "
_JSON_HINT = ' 반드시 {"이름": "...", "국적": "..."} 형식의 JSON으로만 답해.'


"""
사용할 수 있는 모델은 provider.py의 PROVIDERS 딕셔너리를 참고하세요.
model_alias는 LLM을 제공하는 업체의 별칭입니다. (예: "openai", "hyperclova", "claude", "gemini")
model_name은 해당 업체에서 사용할 모델의 이름입니다. (예: "gpt-4o", "gpt-3.5-turbo", "claude-opus-4
"""


response = llm_caller.chat(
    model_alias="openai",
    model_name="gpt-4o",
    messages=[{"role": "user", "content": QUESTION}],
    max_tokens=4096,
)


print(response.text)
print(response.total_tokens, response.latency_s)


def _max_tokens(model_name: str) -> int:
    info = HCX_MODEL_INFO[model_name]
    return min(info["max_output_tokens"], info["context_window"] // 2)


def _call(model_name: str, structured: bool) -> None:
    kwargs: dict = dict(
        model_alias="hyperclova",
        model_name=model_name,
        messages=[{"role": "user", "content": QUESTION}],
        max_tokens=_max_tokens(model_name),
    )

    if structured:
        if model_name == HCX_MODELS[0]:  # HCX-007: v3 native 구조화 출력
            kwargs["json_structure"] = SCHEMA
        else:  # 나머지 HCX: response_format 미지원 — 프롬프트로만 유도
            kwargs["messages"] = [{"role": "user", "content": QUESTION + _JSON_HINT}]

    label = "🀫🀫🀫 구조화 🀫🀫🀫" if structured else "🀫🀫🀫  일반  🀫🀫🀫"
    try:
        response = llm_caller.chat(**kwargs)
        print(f"{label}\n{response.text}")
        print("-" * 40)
        print(f"[ 💰 tokens: {response.total_tokens}, ⌛️ latency: {response.latency_s:.2f}s ]\n")
    except Exception as e:
        print(f"{label}\n실패: {e}")


for model_name in HCX_MODELS:
    print(f"\n{'='*100}")
    print(f"  🍏 [hyperclova] {model_name}")
    print(f"{'='*100}")

    _call(model_name, structured=False)
    # _call(model_name, structured=True)
