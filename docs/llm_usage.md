# `src/llm/` 사용 가이드

## 환경변수 설정

`.env` 파일에 사용할 provider의 키를 추가합니다.

```
# Gemini
GEMINI_API_KEY=...
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/

# HyperCLOVA
CLOVASTUDIO_API_KEY=...
CLOVASTUDIO_BASE_URL=...
```

## 기본 사용법

```python
from src.llm.router import LlmRouter

router = LlmRouter()  # .env 자동 로딩

response = router.chat(
    model_alias="claim-detection-gemini",  # provider.py에 등록된 alias
    model_name="gemini-2.0-flash",         # 실제 모델명
    messages=[{"role": "user", "content": "..."}],
    max_tokens=256,
)

print(response.text)
print(response.total_tokens, response.latency_s)
```

## model_alias vs model_name

| 항목 | 설명 | 예시 |
|---|---|---|
| `model_alias` | 용도 식별자. `provider.py`에 등록 필요 | `claim-detection-gemini` |
| `model_name` | 실제 API에 전달되는 모델명 | `gemini-2.0-flash` |

alias가 `provider.py`에 없으면 `LlmError`가 납니다.

## 응답 구조 (`ChatResponse`)

| 필드 | 타입 | 설명 |
|---|---|---|
| `text` | `str` | 모델 응답 텍스트 |
| `total_tokens` | `int` | 총 사용 토큰 |
| `prompt_tokens` | `int` | 입력 토큰 |
| `completion_tokens` | `int` | 출력 토큰 |
| `latency_s` | `float` | 호출 소요 시간(초) |
| `model` | `str` | 실제 응답한 모델명 |
| `finish_reason` | `str` | 종료 이유 (`stop`, `length` 등) |

## 에러 처리

모든 LLM 호출 실패는 `LlmError`로 통일됩니다.

```python
from src.llm.client import LlmError

try:
    response = router.chat(...)
except LlmError as e:
    # 로깅 후 처리
    print(e)
```
