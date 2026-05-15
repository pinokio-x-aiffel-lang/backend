# LLM 클라이언트 명세서

NCP HyperCLOVA X 채팅 API 호출용 클라이언트. `src/llm/client.py`.

## 한 줄 요약

`ChatClient.fetch_chat()` 한 메서드로 LLM 호출. messages 받아서 `ChatResponse` 돌려주거나 `LlmError` 던짐. **재시도 없음, 호출자 책임이 명확함.**

## 책임 경계

| 책임 | 누가 |
|---|---|
| messages 받아서 SDK 호출 | 클라이언트 |
| 응답 → `ChatResponse` 변환 | 클라이언트 |
| `APIError` → `LlmError` wrap (원본 보존) | 클라이언트 |
| API 키 `.env` 로딩 | 클라이언트 |
| **프롬프트 작성** | **호출자** |
| **JSON → Pydantic 파싱** | **호출자** |
| **재시도** | **호출자** (필요시 옆 유틸) |
| **로깅** | **호출자** |
| **비용 누적** | **호출자** |
| **대화 히스토리** | **호출자** |

## 환경 설정

`.env` 파일에 API 키 설정:

```
HCX_API_KEY=your_ncp_clova_studio_api_key_here
```

기본 endpoint: `https://clovastudio.stream.ntruss.com/v1/openai` (NCP CLOVA OpenAI 호환).

## 공개 API

### `ChatClient(...)` — 생성자

```python
ChatClient(
    api_key: str | None = None,        # None → .env 의 HCX_API_KEY 자동 로드
    base_url: str | None = None,       # None → NCP CLOVA 기본 endpoint
    default_model: str | None = None,  # None → fetch_chat() 시 model 인자 필수
    timeout: float = 60.0,             # 초, fetch_chat() 시 override 가능
)
```

### `ChatClient.fetch_chat(...)` — LLM 호출

```python
def fetch_chat(
    messages: list[dict],              # OpenAI 표준 형식
    model: str | None = None,          # None → default_model
    temperature: float | None = None,  # None → SDK 기본
    max_tokens: int | None = None,     # None → SDK 기본
    json_mode: bool = False,           # True → response_format json_object
    timeout: float | None = None,      # None → 인스턴스 기본
) -> ChatResponse
```

**Raises:**
- `LlmError` — SDK `APIError` 모두 wrap. 원본은 `__cause__` 로 접근.
- `ValueError` — `model` 도 `default_model` 도 None 일 때.

**재시도/타임아웃:**
- SDK 재시도 끔 (`max_retries=0`). 모든 에러 즉시 던짐.
- `timeout` 은 호출 1회 기준 (재시도 없으니 곧 총 시간).

### `ChatResponse` — 응답 dataclass

| 필드 | 타입 | 의미 |
|---|---|---|
| `text` | `str` | LLM 생성 텍스트 |
| `total_tokens` | `int` | 총 토큰 |
| `prompt_tokens` | `int` | 입력 토큰 |
| `completion_tokens` | `int` | 출력 토큰 |
| `model` | `str` | 실제 호출된 모델명 |
| `finish_reason` | `str` | 종료 사유 (`stop`/`length`/`content_filter` 등) |
| `latency_s` | `float` | 호출 소요 시간 (초) |
| `raw` | `dict` | SDK 원본 응답 (디버깅용) |

### `LlmError` — 공통 예외

`openai.APIError` 와 그 하위 (`APITimeoutError`, `RateLimitError`, `AuthenticationError` 등) 가 모두 `LlmError` 로 wrap 됨. 원본은 `__cause__` 로 보존.

## 사용 예시

### 기본 사용 — Claim 추출 (JSON 모드)

```python
from src.llm import ChatClient, LlmError

client = ChatClient(default_model="HCX-005")

try:
    response = client.fetch_chat(
        messages=[
            {"role": "user", "content": "기사에서 수치 주장을 JSON 으로 추출해줘: ..."},
        ],
        temperature=0.1,
        max_tokens=2000,
        json_mode=True,
    )
    print(response.text)         # LLM 응답 텍스트
    print(response.total_tokens) # 토큰 사용량
except LlmError as e:
    # 재시도 없이 즉시 도달
    print(f"실패: {e}, 원인: {e.__cause__}")
```

### 호출자 측 재시도 (옆 유틸 패턴)

클라이언트는 재시도 안 함. 호출자가 필요시 직접 또는 데코레이터로:

```python
def retry_on_llm_error(max_attempts: int = 3):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except LlmError:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(2 ** attempt)
        return wrapper
    return decorator

@retry_on_llm_error(max_attempts=3)
def extract_claim(article_id: str) -> Claims:
    response = client.fetch_chat(messages=[...], model="HCX-005")
    return Claims.model_validate_json(response.text)
```

## 결정 이력 (요약)

| 결정 | 값 | 근거 |
|---|---|---|
| 응답 객체 추상화 | `ChatResponse` dataclass | SDK 의존 격리, dict 변환 단순 |
| 예외 단일화 | `LlmError` 하나 | 호출자 `except LlmError` 한 줄 처리 |
| 메시지 입력 타입 | `list[dict]` | OpenAI 표준, 호출자 작성 쉬움 |
| 노출 파라미터 | `temperature`, `max_tokens`, `json_mode`, `timeout` | PoC 자주 쓰는 4개 |
| 재시도 | **안 함** (`max_retries=0`) | 호출자 통제권, 모듈별 정책 자유 |
| 타임아웃 기본값 | 60초 | 긴 응답 모듈 (설명 생성 등) 여유 |
| 기본 모델 | `None` (호출 시 명시 권장) | PoC 모델 실험 단계, 기본값 묻혀버림 방지 |

자세한 결정 과정은 `memory/project_claim_module_status.md` 의 1-2 / 2-x / 3 항목 참조.
