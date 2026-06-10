"""function_calling 플래그 검증 + 지원 3개 모델 tool calling 테스트.

대상 모듈: src.llm.llm_caller (function_calling 게이트)
작성자: leeaain2027 <leeaain2027@gmail.com>
작성일: 2026-05-26
"""
from src.llm.client import LlmError
from src.llm.llm_caller import LlmCaller
from src.llm.provider import HCX_MODEL_INFO

llm_caller = LlmCaller()

SUPPORTED = ["HCX-005", "HCX-007", "HCX-DASH-002"]
UNSUPPORTED = "HCX-003"  # 지원 목록에 없는 모델

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
                        "description": "KOSIS에서 검색할 통계 키워드",
                    },
                },
                "required": ["search_keyword"],
            },
        },
    }
]
tool_choice = {"type": "function", "function": {"name": "search_kosis_metadata"}}


def _max_tokens(model_name: str) -> int:
    info = HCX_MODEL_INFO[model_name]
    return min(info["max_output_tokens"], info["context_window"] // 2)


def _call(model_name: str) -> None:
    print(f"\n{'='*80}\n  🍏 {model_name} (function_calling=True)\n{'='*80}")
    try:
        response = llm_caller.chat(
            model_alias="hyperclova",
            model_name=model_name,
            messages=messages,
            max_tokens=_max_tokens(model_name),
            function_calling=True,
            tools=tools,
            tool_choice=tool_choice,
        )
        endpoint = "v3 native" if "result" in response.raw else "v1/openai compat"
        body = response.tool_calls if response.tool_calls else response.text
        print(f"통과 [{endpoint}] → {body}")
    except LlmError as e:
        print(f"LlmError: {e}")
    except Exception as e:
        print(f"기타 실패: {type(e).__name__}: {e}")


PERSON_SCHEMA = {
    "type": "object",
    "properties": {
        "이름": {"type": "string", "description": "인물 이름"},
        "국적": {"type": "string", "description": "인물 국적"},
    },
    "required": ["이름", "국적"],
    "additionalProperties": False,
}
person_messages = [
    {"role": "user", "content": "세종대왕에 대해 이름과 국적을 알려줘."},
]


def _call_structured(model_name: str) -> None:
    print(f"\n{'='*80}\n  📐 {model_name} (structured outputs)\n{'='*80}")
    try:
        response = llm_caller.chat(
            model_alias="hyperclova",
            model_name=model_name,
            messages=person_messages,
            max_tokens=_max_tokens(model_name),
            json_structure=PERSON_SCHEMA,
        )
        endpoint = "v3 native" if "result" in response.raw else "v1/openai compat"
        print(f"통과 [{endpoint}] → {response.text}")
    except LlmError as e:
        print(f"LlmError: {e}")
    except Exception as e:
        print(f"기타 실패: {type(e).__name__}: {e}")


# 1) 지원 3개 모델 — function calling
for m in SUPPORTED:
    _call(m)

# 1-b) 지원 3개 모델 — structured outputs (v3 native 경로 확인)
for m in SUPPORTED:
    _call_structured(m)

# 2) 미지원 HCX 모델 → print + LlmError 기대
print(f"\n{'='*80}\n  ❌ {UNSUPPORTED} (function_calling=True, 미지원 기대)\n{'='*80}")
try:
    llm_caller.chat(
        model_alias="hyperclova",
        model_name=UNSUPPORTED,
        messages=messages,
        max_tokens=_max_tokens(UNSUPPORTED),
        function_calling=True,
        tools=tools,
        tool_choice=tool_choice,
    )
    print("⚠️  예외가 발생하지 않음 — 게이트 실패")
except LlmError as e:
    print(f"기대대로 차단됨 → LlmError: {e}")

# 3) 비(非)HCX 벤더 — 실제 지원하므로 통과 + tool_calls 기대 (실호출)
PASS_VENDORS = [
    ("openai", "gpt-4o-mini"),
    ("gemini", "gemini-2.5-flash"),
    ("claude", "claude-haiku-4-5-20251001"),
]
print(f"\n{'='*80}\n  🌐 비(非)HCX 벤더 (function_calling=True, 통과 기대)\n{'='*80}")
for model_alias, model_name in PASS_VENDORS:
    print(f"\n--- {model_alias} / {model_name} ---")
    try:
        r = llm_caller.chat(
            model_alias=model_alias,
            model_name=model_name,
            messages=messages,
            function_calling=True,
            tools=tools,
            tool_choice=tool_choice,
        )
        print(f"{'✅ 통과 → ' + str(r.tool_calls) if r.tool_calls else '⚠️ tool_calls 없음'}")
    except LlmError as e:
        print(f"❌ 예기치 않은 차단 → LlmError: {e}")

# 3-b) function calling 미지원으로 여전히 차단되어야 하는 모델 (네트워크 없이 검증)
#      HCX-003/DASH-001만 차단 (GPT Responses 계열은 이제 tools 변환 전송으로 지원됨)
BLOCK_MODELS = [
    ("hyperclova", "HCX-003"),
    ("hyperclova", "HCX-DASH-001"),
]
print(f"\n{'='*80}\n  🚫 여전히 차단되어야 하는 모델 (function_calling=True)\n{'='*80}")
for model_alias, model_name in BLOCK_MODELS:
    try:
        llm_caller.chat(
            model_alias=model_alias, model_name=model_name, messages=messages,
            max_tokens=2048, function_calling=True, tools=tools, tool_choice=tool_choice,
        )
        print(f"  [{model_alias}/{model_name}] → ⚠️ 차단 안 됨!")
    except LlmError as e:
        print(f"  [{model_alias}/{model_name}] → ✅ 차단: {e}")

# 3-c) max_tokens 1024 하한은 HCX 전용 — GPT는 512여도 통과해야 함 (실호출)
print(f"\n{'='*80}\n  🔢 max_tokens 하한은 HCX 전용 (gpt-4o-mini, max_tokens=512)\n{'='*80}")
try:
    r = llm_caller.chat(
        model_alias="openai", model_name="gpt-4o-mini", messages=messages,
        max_tokens=512, function_calling=True, tools=tools, tool_choice=tool_choice,
    )
    print(f"  {'✅ 통과(차단 안 됨) → ' + str(r.tool_calls) if r.tool_calls else '⚠️ tool_calls 없음'}")
except LlmError as e:
    print(f"  ❌ 잘못 차단됨 → {e}")

# 4) max_tokens 하한(1024) 가드 — provider 조회 전이라 잘못된 alias로 네트워크 없이 검증
print(f"\n{'='*80}\n  🔢 max_tokens 하한 가드 (function_calling=True, HCX-005)\n{'='*80}")
for mt in [None, 512, 1023, 1024, 2048]:
    try:
        llm_caller.chat(
            model_alias="__invalid__",  # max_tokens 가드 통과 시 provider 에러로 갈림
            model_name="HCX-005",
            messages=messages,
            max_tokens=mt,
            function_calling=True,
            tools=tools,
            tool_choice=tool_choice,
        )
    except LlmError as e:
        s = str(e)
        if "max_tokens는" in s:
            print(f"  max_tokens={str(mt):<5} → ⛔ 차단: {s}")
        elif "등록되지 않은 provider" in s:
            print(f"  max_tokens={str(mt):<5} → ✅ 가드 통과 (provider 단계 도달)")
        else:
            print(f"  max_tokens={str(mt):<5} → ❓ {s}")
