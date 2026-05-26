# fake-news-detector

아이펠 엔지니어 1기 기업프로젝트

## Fast API 서버 띄우기

```bash
uv run uvicorn main:app --reload
```

브라우저 확인

```bash
http://127.0.0.1:8000/docs
```

요청 테스트

```bash
curl -X POST "http://127.0.0.1:8000/verify" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "통계청에 따르면 2024년 합계출산율은 0.72명이다."
  }'
```

### frontend 분리

https://github.com/pinokio-x/fake-news-detector-frontend

---

## LLM 호출 (`src/llm`)

### 파일 역할

| 파일 | 하는 일 |
|---|---|
| **`provider.py`** | 모델 메타데이터/정책 정의. 벤더별 endpoint·API 키 환경변수(`ProviderConfig`, `PROVIDERS`), 모델 목록(`GPT_MODELS`/`GEMINI_MODELS`/`CLAUDE_MODELS`/HCX), 그리고 기능 지원 집합(`FUNCTION_CALLING_MODELS`, `HCX_NATIVE_MODELS`, `HCX_THINKING_MODELS`, `HCX_STRUCTURED_OUTPUT_MODELS` 등)을 담는다. **호출 로직은 없음.** |
| **`client.py`** | 실제 1회 호출 담당. `ChatClient.fetch_chat`(OpenAI 호환 `/chat/completions`), `ChatClient.fetch_responses`(OpenAI `/responses`), `fetch_hcx_native`(HCX v3 native)로 LLM을 호출하고 `ChatResponse`로 정규화한다. 재시도·로깅·비용계산·provider 선택은 하지 않음. |
| **`llm_caller.py`** | 진입점(`LlmCaller.chat`). `model_alias`/`model_name`을 받아 ① 옵션 가드 검증 → ② provider 해석 → ③ 적절한 `client` 메서드로 라우팅한다. 모든 호출 전 검증(가드)이 여기 모여 있다. |

### 공통 호출

```python
from src.llm.llm_caller import LlmCaller

llm = LlmCaller()
resp = llm.chat(
    model_alias="openai",          # "openai" | "hyperclova" | "claude" | "gemini"
    model_name="gpt-4o-mini",
    messages=[{"role": "user", "content": "안녕"}],
    # 선택 옵션 ↓
    temperature=None,
    max_tokens=None,
    json_mode=False,               # {"type":"json_object"} 모드
    json_structure=None,           # structured outputs용 JSON schema(dict)
    function_calling=False,        # tool 사용 시 True (+ tools/tool_choice)
    thinking=False,                # 추론 모드 (HCX-007 전용)
    thinking_effort=None,          # "none"|"low"|"medium"|"high" (HCX-007 일반 호출)
    tools=None,
    tool_choice=None,
    timeout=None,
)
resp.text          # 텍스트 응답
resp.tool_calls    # function calling 결과(list) 또는 None
```

### 가드 규칙 (위반 시 `LlmError`)

- `function_calling=True`는 `FUNCTION_CALLING_MODELS`에 포함된 모델만 허용.
- HCX function calling은 `max_tokens >= 1024` 필수. **`None`이면 1024로 자동 보정**, 명시적으로 1024 미만이면 차단(타 벤더는 이 제약 없음).
- `json_structure`(structured outputs)는 HCX 중 **HCX-007만** 허용(나머지 HCX 차단).
- `thinking=True`는 **HCX-007만** 허용.
- HCX native(005/007/DASH-002)는 function calling / structured outputs / thinking **중 하나만** 동시 사용 가능(2개 이상이면 차단).
- `json_mode=True`는 `supports_json_object`인 provider(OpenAI·Gemini)만 허용(HCX·Claude 차단).

---

## 모델별 호출 가이드

옵션 표기: ✅ 가능 / ❌ 불가(가드 차단 또는 API 거부)

### HyperCLOVA X (`model_alias="hyperclova"`)

| 모델 | 경로 | function_calling | json_structure | thinking | json_mode |
|---|---|:--:|:--:|:--:|:--:|
| **HCX-007** | v3 native | ✅ | ✅ | ✅ | ❌ |
| **HCX-005** | v3 native | ✅ | ❌ | ❌ | ❌ |
| **HCX-DASH-002** | v3 native | ✅ | ❌ | ❌ | ❌ |
| **HCX-003** | v1 compat | ❌ | ❌ | ❌ | ❌ |
| **HCX-DASH-001** | v1 compat | ❌ | ❌ | ❌ | ❌ |

> HCX-007의 세 기능(FC/structured/thinking)은 **동시에 하나만** 쓸 수 있습니다. function calling은 `max_tokens >= 1024` 필요.
>
> **thinking.effort**: HCX-007의 추론 강도는 `none` / `low` / `medium` / `high`로 조절할 수 있습니다(실호출 검증값 — `mid`는 400, `medium`이 정상. `none`은 추론 비활성화). `chat(..., thinking_effort="high")`로 지정하며, 일반 호출(FC·structured 미사용)에서만 적용됩니다. function calling·structured outputs 사용 시에는 충돌 방지를 위해 `effort:none`이 자동 전송됩니다.

```python
# HCX-007 — 일반 (추론은 기본 ON)
llm.chat(model_alias="hyperclova", model_name="HCX-007",
         messages=[{"role": "user", "content": "출산율 추세 분석해줘"}], max_tokens=4096)

# HCX-007 — structured outputs (thinking/FC와 동시 불가)
llm.chat(model_alias="hyperclova", model_name="HCX-007",
         messages=[{"role": "user", "content": "세종대왕 정보"}],
         json_structure={"type": "object", "properties": {"이름": {"type": "string"}},
                         "required": ["이름"]}, max_tokens=4096)

# HCX-007 / HCX-005 / HCX-DASH-002 — function calling (max_tokens>=1024 필수)
llm.chat(model_alias="hyperclova", model_name="HCX-005",
         messages=[{"role": "user", "content": "2020년 농가 고령 인구"}],
         function_calling=True, tools=TOOLS, tool_choice=TOOL_CHOICE, max_tokens=1024)

# HCX-007 — thinking 추론 강도 지정 (function_calling/json_structure는 False여야 함)
llm.chat(model_alias="hyperclova", model_name="HCX-007",
         messages=[{"role": "user", "content": "단계적으로 추론해줘"}],
         thinking_effort="high", max_tokens=4096)   # none/low/medium/high

# HCX-003 / HCX-DASH-001 — 일반 대화만 가능 (FC/structured/thinking 전부 ❌)
llm.chat(model_alias="hyperclova", model_name="HCX-003",
         messages=[{"role": "user", "content": "안녕"}], max_tokens=1024)
```

### OpenAI GPT (`model_alias="openai"`)

대상: `gpt-5.5/5.4/5` 계열, `gpt-4.1/4o` 계열, `o3/o4-mini/o1`, 레거시(`gpt-4-turbo/gpt-4/gpt-3.5-turbo`).

| 기능 | 지원 범위 |
|---|---|
| function_calling | **전 모델 ✅** (Responses 계열 `gpt-5.x-pro`/`o1-pro` 포함 — 실호출 검증됨) |
| json_structure | gpt-4o 이상 ✅ / 레거시(`gpt-4-turbo`,`gpt-4`,`gpt-3.5-turbo`) ❌ |
| json_mode | ✅ |
| thinking | ❌ (HCX 전용 옵션. o-series 추론은 자동) |

```python
# 일반 / structured / json_mode
llm.chat(model_alias="openai", model_name="gpt-4o-mini",
         messages=[{"role": "user", "content": "안녕"}])
llm.chat(model_alias="openai", model_name="gpt-5", json_mode=True,
         messages=[{"role": "user", "content": '{"answer": ...} 형식으로'}])

# function calling — 일반 모델
llm.chat(model_alias="openai", model_name="gpt-4o-mini",
         messages=msgs, function_calling=True, tools=TOOLS, tool_choice=TOOL_CHOICE)

# function calling — Responses 계열(pro)은 응답이 느리니 timeout 여유있게
llm.chat(model_alias="openai", model_name="gpt-5-pro",
         messages=msgs, function_calling=True, tools=TOOLS, tool_choice=TOOL_CHOICE,
         max_tokens=2048, timeout=300)
```

> `gpt-5.5-pro`/`gpt-5.4-pro`/`gpt-5-pro`/`o1-pro`는 `/v1/responses` 경로로 호출됩니다. function calling은 지원하지만 `json_mode`/`json_structure`는 이 경로에 연결돼 있지 않습니다.

### Google Gemini (`model_alias="gemini"`)

모두 Google `v1beta` OpenAI 호환 endpoint(`/v1beta/openai/`)로 호출됩니다. **"v3"는 HCX 전용 개념이며 Gemini에는 해당 없음** — 전 Gemini 모델이 동일한 `fetch_chat`(OpenAI 호환) 경로를 씁니다.

대상: `gemini-3.5-flash`, `gemini-3.1-flash-lite`, `gemini-3-flash-preview`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`.
※ `gemini-3.1-flash-lite-preview`는 더 이상 제공되지 않음(호출 시 404).

| 기능 | 지원 |
|---|:--:|
| function_calling | ✅ (현재 제공되는 모델 전부, 실호출 검증됨) |
| json_structure | ✅ |
| json_mode | ✅ |
| thinking | ❌ |

```python
llm.chat(model_alias="gemini", model_name="gemini-2.5-flash",
         messages=msgs, function_calling=True, tools=TOOLS, tool_choice=TOOL_CHOICE)
```

### Anthropic Claude (`model_alias="claude"`)

대상: `claude-opus-4-7`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`, 레거시(`claude-opus-4-6`, `claude-sonnet-4-5-20250929`, `claude-opus-4-5-20251101`, `claude-opus-4-1-20250805`).

| 기능 | 지원 |
|---|:--:|
| function_calling | ✅ (전 모델, 실호출 검증됨) |
| json_structure | ❌ (구조화 출력 미지원) |
| json_mode | ❌ (`supports_json_object=False` → 차단) |
| thinking | ❌ |

```python
llm.chat(model_alias="claude", model_name="claude-haiku-4-5-20251001",
         messages=msgs, function_calling=True, tools=TOOLS, tool_choice=TOOL_CHOICE)
```
