from src.llm.llm_caller import LlmCaller
from src.llm.provider import (
    CLAUDE_MODELS,
    GEMINI_MODELS,
    GPT_MODELS,
    NO_STRUCTURED_OUTPUT_MODELS,
    HCX_MODEL_INFO,
    HCX_MODELS,
)

llm_caller = LlmCaller()

QUESTION = "지금 미국 대통령은 누구지?"

SCHEMA = {
    "type": "object",
    "properties": {
        "이름": {"type": "string", "description": "Person's name"},
        "국적": {"type": "string", "description": "Person's nationality"},
    },
    "required": ["이름", "국적"],
    "additionalProperties": False,
}

ALL_MODELS: dict[str, list[str]] = {
    "openai": GPT_MODELS,
    "hyperclova": HCX_MODELS,
    "gemini": GEMINI_MODELS,
    "claude": CLAUDE_MODELS,
}


def _max_tokens(model_alias: str, model_name: str) -> int:
    if model_alias == "hyperclova":
        info = HCX_MODEL_INFO[model_name]
        return min(info["max_output_tokens"], info["context_window"] // 2)
    return 4096


_JSON_HINT = ' 반드시 {"이름": "...", "국적": "..."} 형식의 JSON으로만 답해.'


def _supports_structured(model_name: str) -> bool:
    return model_name not in NO_STRUCTURED_OUTPUT_MODELS


def _call(model_alias: str, model_name: str, structured: bool) -> None:
    label = "🀫🀫🀫 구조화 🀫🀫🀫" if structured else "🀫🀫🀫  일반  🀫🀫🀫"

    if structured and not _supports_structured(model_name):
        print(f"{label}\n구조화를 지원하지 않는 모델\n")
        return

    kwargs: dict = dict(
        model_alias=model_alias,
        model_name=model_name,
        messages=[{"role": "user", "content": QUESTION}],
        max_tokens=_max_tokens(model_alias, model_name),
    )

    if structured:
        if model_alias == "hyperclova":
            if model_name == HCX_MODELS[0]:  # HCX-007: v3 native 구조화 출력
                kwargs["json_structure"] = SCHEMA
            else:  # 나머지 HCX: response_format 미지원 — 프롬프트로만 유도
                kwargs["messages"] = [{"role": "user", "content": QUESTION + _JSON_HINT}]
        else:
            kwargs["json_structure"] = SCHEMA

    try:
        response = llm_caller.chat(**kwargs)
        print(f"{label}\n{response.text}")
        print("-" * 40)
        print(f"[ 💰 tokens: {response.total_tokens}, ⌛️ latency: {response.latency_s:.2f}s ]\n")
    except Exception as e:
        print(f"{label} 실패: {e}")


for model_alias, models in ALL_MODELS.items():
    for model_name in models:
        print(f"\n{'='*100}")
        print(f"  🍏 [{model_alias}] {model_name}")
        print(f"{'='*100}")

        _call(model_alias, model_name, structured=False)
        _call(model_alias, model_name, structured=True)
