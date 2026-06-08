"""HCX 단일 호출 테스트.

대상 모듈: src.llm.llm_caller (HCX 모델)
작성자: leeaain2027 <leeaain2027@gmail.com>
작성일: 2026-05-26
"""
from src.llm.llm_caller import LlmCaller
from src.llm.provider import HCX_MODEL_INFO, HCX_MODELS

"""
    "HCX-007":      {"context_window": 128_000, "max_output_tokens": 32_768},
    "HCX-005":      {"context_window": 128_000, "max_output_tokens":  4_096},
    "HCX-DASH-002": {"context_window":  32_000, "max_output_tokens":  4_096},
    "HCX-003":      {"context_window":   7_600, "max_output_tokens":  4_096},
    "HCX-DASH-001": {"context_window":   3_500, "max_output_tokens":  4_096},
"""


llm_caller = LlmCaller()

model_name = HCX_MODELS[1]

# 사용자 메시지 정의
QUESTION = "2020년 전국 농가 고령 인구 합계 조사해줘"
messages = [
    {
        "role": "system",
        "content": (
            "너는 직접 답하지 않는다. 사용자 질문에 답하려면 반드시 제공된 도구 중 "
            "하나를 호출해 어떤 검색 요청을 보낼지 결정해라. 자연어로 답하지 마라."
        ),
    },
    {"role": "user", "content": QUESTION},
]


#  모델이 호출할 수 있도록 정의할 함수 목록 (Tools)
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_kosis_metadata",
            "description": "KOSIS(국가통계포털) 통합검색 API를 호출하여 입력한 검색어와 연관된 통계표 메타데이터 목록을 가져옵니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_keyword": {
                        "type": "string",
                        "description": "KOSIS에서 검색할 통계 키워드 (예: '농가 고령 인구', '출산율')"
                    },
                    "result_count": {
                        "type": "integer",
                        "description": "가져올 결과의 최대 개수 (기본값 5)",
                        "default": 5
                    }
                },
                "required": ["search_keyword"]
            }
        }
    }
]


SCHEMA = {
    "type": "object",
    "properties": {
        "이름": {"type": "string", "description": "Person's name"},
        "국적": {"type": "string", "description": "Person's nationality"},
    },
    "required": ["이름", "국적"],
    "additionalProperties": False,
}
_JSON_HINT = ' 반드시 {"이름": "...", "국적": "..."} 형식의 JSON으로만 답해.'


def _max_tokens(model_name: str) -> int:
    info = HCX_MODEL_INFO[model_name]
    return min(info["max_output_tokens"], info["context_window"] // 2)


def _call(model_name: str, structured: bool, use_tools: bool = False) -> None:
    kwargs: dict = dict(
        model_alias="hyperclova",
        model_name=model_name,
        messages=messages,
        max_tokens=_max_tokens(model_name),
    )

    if use_tools:
        kwargs["tools"] = tools
        # HCX는 "required" 미지원 → 특정 함수 강제 객체로 MCP 호출 강제
        kwargs["tool_choice"] = {
            "type": "function",
            "function": {"name": "search_kosis_metadata"},
        }
    elif structured:
        if model_name == HCX_MODELS[0]:  # HCX-007: v3 native 구조화 출력
            kwargs["json_structure"] = SCHEMA
        else:  # 나머지 HCX: response_format 미지원 — 프롬프트로만 유도
            kwargs["messages"] = [{"role": "user", "content": QUESTION + _JSON_HINT}]

    if use_tools:
        label = "🀫🀫🀫 tool calling 🀫🀫🀫"
    elif structured:
        label = "🀫🀫🀫 구조화 🀫🀫🀫"
    else:
        label = "🀫🀫🀫  일반  🀫🀫🀫"
    try:
        response = llm_caller.chat(**kwargs)
        body = response.tool_calls if response.tool_calls else response.text
        print(f"{label}\n{body}")
        print("-" * 40)
        print(f"[ 💰 tokens: {response.total_tokens}, ⌛️ latency: {response.latency_s:.2f}s ]\n")
    except Exception as e:
        print(f"{label}\n실패: {e}")


print(f"\n{'='*100}")
print(f"  🍏 [hyperclova] {model_name}")
print(f"{'='*100}")

_call(model_name, structured=False)
_call(model_name, structured=True)
_call(model_name, structured=False, use_tools=True)