"""모든 HCX 모델 × 4개 시나리오 테스트.

1. 추론(thinking) 모드만 켜고 질문      → HCX-007만 통과 기대
2. structured outputs + function calling 동시 → 동시 사용 차단 기대
3. structured outputs만 켜고 구조화 응답  → HCX-007만 통과, 나머지 HCX는 호출 전 차단 기대
4. function calling만 켜고 tool call 응답 → native 3종(005/007/DASH-002) 통과, 003/DASH-001 차단 기대

대상 모듈: src.llm.llm_caller (HCX 모델 × 시나리오)
작성자: leeaain2027 <leeaain2027@gmail.com>
작성일: 2026-05-20
"""
from src.llm.client import LlmError
from src.llm.llm_caller import LlmCaller
from src.llm.provider import HCX_MODEL_INFO, HCX_MODELS

llm_caller = LlmCaller()

TOOLS = [{
    "type": "function",
    "function": {
        "name": "search_kosis_metadata",
        "description": "KOSIS(국가통계포털) 통합검색 API로 통계표 메타데이터를 가져온다.",
        "parameters": {
            "type": "object",
            "properties": {"search_keyword": {"type": "string", "description": "검색 키워드"}},
            "required": ["search_keyword"],
        },
    },
}]
TOOL_CHOICE = {"type": "function", "function": {"name": "search_kosis_metadata"}}

PERSON_SCHEMA = {
    "type": "object",
    "properties": {
        "이름": {"type": "string", "description": "인물 이름"},
        "국적": {"type": "string", "description": "인물 국적"},
    },
    "required": ["이름", "국적"],
    "additionalProperties": False,
}


def _max_tokens(model_name: str) -> int:
    info = HCX_MODEL_INFO[model_name]
    return min(info["max_output_tokens"], info["context_window"] // 2)


def _chat(model_name: str, messages: list[dict], **kw) -> str:
    try:
        r = llm_caller.chat(
            model_alias="hyperclova",
            model_name=model_name,
            messages=messages,
            max_tokens=_max_tokens(model_name),
            **kw,
        )
        endpoint = "v3 native" if "result" in r.raw else "v1 compat"
        body = r.tool_calls if r.tool_calls else r.text
        return f"✅ 통과 [{endpoint}] → {body}"
    except LlmError as e:
        return f"⛔ 차단/실패 → {e}"
    except Exception as e:
        return f"❓ 기타 실패 → {type(e).__name__}: {e}"


SCENARIOS = [
    (
        "1. 추론(thinking)만",
        dict(thinking=True),
        [{"role": "user", "content": "최근 한국 합계출산율 추세를 단계적으로 분석해줘."}],
    ),
    (
        "2. structured + FC 동시",
        dict(function_calling=True, json_structure=PERSON_SCHEMA, tools=TOOLS, tool_choice=TOOL_CHOICE),
        [{"role": "user", "content": "세종대왕에 대해 알려줘."}],
    ),
    (
        "3. structured만",
        dict(json_structure=PERSON_SCHEMA),
        [{"role": "user", "content": "세종대왕의 이름과 국적을 알려줘."}],
    ),
    (
        "4. function calling만",
        dict(function_calling=True, tools=TOOLS, tool_choice=TOOL_CHOICE),
        [
            {"role": "system", "content": "반드시 제공된 도구를 호출해라. 자연어로 답하지 마라."},
            {"role": "user", "content": "2020년 전국 농가 고령 인구 조사해줘"},
        ],
    ),
]

for model in HCX_MODELS:
    print(f"\n{'='*90}\n  🍏 {model}\n{'='*90}")
    for label, kw, messages in SCENARIOS:
        print(f"  [{label}]\n    {_chat(model, messages, **kw)}")
