# LLM Chat API 서버 구현 — 필수 조건 및 플랜
 
> **목적**: 기존 Chat Client 모듈을 FastAPI 기반 REST API 서버로 래핑하여, 멀티 LLM Provider(HCX, OpenAI, 기타 오픈소스)를 통합 호출할 수 있는 PoC 수준의 로컬 서버를 구축한다.
> **스코프**: 로컬 PoC (Docker/Cloud Run 미포함, `uvicorn` 직접 실행)
> **작성일**: 2026-05-19
 
---
 
## 1. 핵심 컨셉
 
- **기존 Chat Client는 그대로 둔다.** FastAPI는 HTTP ↔ Chat Client 사이의 얇은 어댑터 역할만 수행한다.
- **멀티 Provider 추상화는 한 겹만.** Over-engineering 금지. `ChatProvider` 인터페이스 + Registry 패턴으로 충분하다.
- **OpenAI 호환 스키마**를 채택한다. 사실상의 업계 표준이고, 평가셋 측정·데모 UI 등 다운스트림 모듈이 SDK를 갈아끼울 때 클라이언트 코드 수정이 거의 없다.
- **세션은 stateless로 처리한다.** 서버는 대화 히스토리를 저장하지 않고, 클라이언트가 매 요청마다 `messages` 배열 전체를 보낸다. PoC 단계 운영 부담 최소화.
- **시크릿(API 키)은 코드 밖에서 관리한다.** HCX는 Infisical, 그 외는 `.env`를 1순위로 사용한다.
---
 
## 2. 폴더 구조
 
```
api/
├── main.py                 # FastAPI 앱, 라우터 등록, 글로벌 예외 핸들러
├── config.py               # 환경변수 로드 (.env)
├── schemas.py              # Pydantic 요청/응답 모델
├── deps.py                 # get_provider() 의존성 주입
├── secrets/
│   ├── __init__.py
│   ├── base.py             # SecretProvider 인터페이스
│   ├── infisical_client.py # Infisical 연동 (HCX 전용)
│   └── env_client.py       # os.environ fallback
├── providers/
│   ├── __init__.py
│   ├── base.py             # ChatProvider 인터페이스 (추상)
│   ├── hcx.py              # HyperCLOVA X 어댑터 (Infisical 사용)
│   ├── openai.py           # OpenAI 어댑터 (.env 사용)
│   ├── local.py            # 로컬/오픈소스 모델 어댑터 (확장용)
│   └── registry.py         # provider_name → instance 매핑
├── routers/
│   └── chat.py             # /v1/chat, /v1/chat/stream
├── logging_utils.py        # JSONL 요청·응답 로깅
.env
.env.example
requirements.txt
run.sh                      # uvicorn 실행 스크립트
README.md
```
 
**확장성 고려**: Provider를 추가할 때는 `providers/` 아래 어댑터 1개 + `registry.py`에 등록 1줄만 추가하면 된다.
 
---
 
## 3. 엔드포인트 명세
 
| 메서드 | 경로 | 용도 |
|---|---|---|
| `POST` | `/v1/chat` | 단일 turn + 멀티 turn (history 배열 입력) |
| `POST` | `/v1/chat/stream` | SSE 스트리밍 응답 |
| `GET`  | `/health` | liveness check |
| `GET`  | `/v1/providers` | 현재 사용 가능한 provider 목록 반환 (디버깅용) |
 
### 3.1 요청 스키마 (`POST /v1/chat`)
 
```json
{
  "provider": "hcx-003",
  "messages": [
    {"role": "system", "content": "당신은 팩트체크 어시스턴트입니다."},
    {"role": "user", "content": "2024년 합계출산율은?"}
  ],
  "temperature": 0.3,
  "max_tokens": 1024,
  "top_p": 0.9
}
```
 
### 3.2 응답 스키마 (non-stream)
 
```json
{
  "provider": "hcx-003",
  "content": "2024년 합계출산율은 0.72명입니다.",
  "usage": {"input_tokens": 123, "output_tokens": 456},
  "latency_ms": 1234,
  "request_id": "req_abc123"
}
```
 
### 3.3 응답 스키마 (SSE 스트리밍)
 
```
event: token
data: {"delta": "2024년"}
 
event: token
data: {"delta": " 합계출산율은"}
 
event: done
data: {"usage": {...}, "latency_ms": 1234}
```
 
---
 
## 4. 시크릿 관리 — Infisical 통합 ⭐
 
### 4.1 정책
 
| Provider | 시크릿 소스 | 키 이름 (예시) |
|---|---|---|
| `hcx-*` (HyperCLOVA X 전 버전) | **Infisical** | `HCX_API_KEY`, `HCX_APIGW_KEY` |
| `openai-*` | `.env` | `OPENAI_API_KEY` |
| `local-*` (로컬 모델) | 불필요 | — |
 
**HCX는 반드시 Infisical을 통해서만 키를 가져온다.** `.env`에 HCX 키를 두지 않는다. 키 유출 위험과 환경별 시크릿 분리(dev/staging/prod) 때문이다.
 
### 4.2 Infisical 연동 방식
 
**Universal Auth (Machine Identity) 사용**을 기본으로 한다. 로컬 PoC라도 개인 토큰보다 머신 자격증명이 안전하고, 추후 CI/CD 이전 시에도 같은 코드가 동작한다.
 
`.env`에 다음 메타데이터만 둔다 (실제 시크릿 값은 두지 않는다):
 
```bash
# .env
INFISICAL_CLIENT_ID=...
INFISICAL_CLIENT_SECRET=...
INFISICAL_PROJECT_ID=...
INFISICAL_ENVIRONMENT=dev
INFISICAL_SITE_URL=https://app.infisical.com   # self-hosted라면 변경
INFISICAL_SECRET_PATH=/
```
 
### 4.3 SecretProvider 인터페이스
 
```python
# secrets/base.py
from abc import ABC, abstractmethod
 
class SecretProvider(ABC):
    @abstractmethod
    def get(self, key: str) -> str: ...
```
 
```python
# secrets/infisical_client.py (의사 코드)
class InfisicalSecretProvider(SecretProvider):
    def __init__(self, client_id, client_secret, project_id, environment, ...):
        self._client = InfisicalSDKClient(...)
        self._client.auth.universal_auth.login(client_id, client_secret)
        self._cache: dict[str, str] = {}
 
    def get(self, key: str) -> str:
        if key in self._cache:
            return self._cache[key]
        secret = self._client.secrets.get_secret_by_name(
            secret_name=key,
            project_id=self.project_id,
            environment_slug=self.environment,
            secret_path=self.secret_path,
        )
        self._cache[key] = secret.secretValue
        return secret.secretValue
```
 
### 4.4 HCX Provider에서 사용
 
```python
# providers/hcx.py (의사 코드)
class HCXProvider(ChatProvider):
    def __init__(self, secret_provider: SecretProvider, model: str):
        self._api_key = secret_provider.get("HCX_API_KEY")
        self._apigw_key = secret_provider.get("HCX_APIGW_KEY")
        self._model = model
        # 기존 Chat Client를 내부에 보관
        self._client = ExistingHCXChatClient(api_key=..., ...)
 
    async def chat(self, messages, **kwargs) -> ChatResult:
        # 기존 Chat Client 호출을 그대로 위임
        ...
```
 
### 4.5 키 로딩 타이밍
 
- **앱 기동 시 1회 fetch + 메모리 캐싱**이 기본.
- 키 만료/갱신은 PoC 범위 밖. 필요하면 TTL 캐시로 확장.
- Infisical 연결 실패 시 **앱 기동 자체를 실패**시킨다 (Fail-fast). HCX provider가 로딩되지 않은 상태로 서버가 뜨면 디버깅이 어렵다.
### 4.6 보안 체크
 
- `.env`, Infisical 자격증명은 **반드시 `.gitignore`** 등록.
- 로그에 시크릿 값이 절대 찍히지 않도록 로깅 마스킹 필수 (`logging_utils.py`).
- `.env.example`은 키 이름만 두고 값은 빈칸으로.
---
 
## 5. ChatProvider 인터페이스
 
```python
# providers/base.py
from abc import ABC, abstractmethod
from typing import AsyncIterator
 
class ChatProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> ChatResult: ...
 
    @abstractmethod
    async def stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]: ...
```
 
```python
# providers/registry.py
def build_registry(settings, secret_provider) -> dict[str, ChatProvider]:
    return {
        "hcx-dash-001": HCXProvider(secret_provider, model="HCX-DASH-001"),
        "hcx-003": HCXProvider(secret_provider, model="HCX-003"),
        "hcx-005": HCXProvider(secret_provider, model="HCX-005"),
        "hcx-007": HCXProvider(secret_provider, model="HCX-007"),
        "openai-gpt-4o": OpenAIProvider(api_key=settings.openai_api_key, model="gpt-4o"),
        # local 모델은 추후 추가
    }
```
 
각 어댑터는 **기존 Chat Client를 내부에서 호출**하기만 한다. 재작성하지 않는다.
 
---
 
## 6. 의사결정 사항 (확정값)
 
| 항목 | 결정 | 이유 |
|---|---|---|
| 인증 | **생략** | 로컬 PoC 한정 |
| 에러 스키마 | **통일** (`{"error": {"code": "...", "message": "..."}}`) | 클라이언트 단순화 |
| 로깅 | **JSONL ON** (요청·응답 전문) | 평가셋 구축·재현성 |
| 시크릿 마스킹 | **필수** | 로그에 키 노출 방지 |
| 타임아웃 | **공통 60초** | provider별 차이는 PoC 범위 밖 |
| 재시도 | **없음** | 클라이언트 책임 |
| 세션 저장 | **없음 (stateless)** | OpenAI/Anthropic 표준 |
| Infisical 인증 | **Universal Auth (Machine Identity)** | 토큰보다 안전, CI/CD 이전 용이 |
| 키 fetch 타이밍 | **앱 기동 시 1회 + 메모리 캐싱** | 호출당 fetch 비용 회피 |
| Infisical 실패 정책 | **Fail-fast (앱 기동 실패)** | 디버깅 명료성 |
 
---
 
## 7. 의존성 (`requirements.txt`)
 
```text
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.0
pydantic-settings>=2.0
python-dotenv>=1.0
httpx>=0.27         # 비동기 HTTP (필요 시)
sse-starlette>=2.0  # SSE 스트리밍 헬퍼
infisicalsdk>=1.0   # Infisical Python SDK
```
 
> **주의**: Infisical Python SDK는 최근(2024년 전후) 패키지 이름이 변경된 이력이 있다. 실제 설치 전 `pip search` 또는 PyPI에서 최신 패키지명·버전을 확인할 것 (`infisical-python`, `infisicalsdk` 등).
 
---
 
## 8. 환경변수 (`.env.example`)
 
```bash
# === 서버 ===
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=INFO
LOG_DIR=./logs
 
# === Infisical (HCX 전용) ===
INFISICAL_CLIENT_ID=
INFISICAL_CLIENT_SECRET=
INFISICAL_PROJECT_ID=
INFISICAL_ENVIRONMENT=dev
INFISICAL_SITE_URL=https://app.infisical.com
INFISICAL_SECRET_PATH=/
 
# === OpenAI (직접 .env 관리) ===
OPENAI_API_KEY=
 
# === 기본 Provider 설정 ===
DEFAULT_TIMEOUT_SECONDS=60
```
 
---
 
## 9. 구현 순서 (4단계)
 
| 단계 | 작업 | 산출물 | 완료 기준 |
|---|---|---|---|
| **1** | FastAPI 스켈레톤 + `/health` + 더미 `/v1/chat` | 빈 라우터, Pydantic 스키마 | `curl localhost:8000/health` → 200 |
| **2** | `SecretProvider` + Infisical 클라이언트 + 앱 기동 시 HCX 키 로딩 | `secrets/` 모듈, fail-fast 동작 | 잘못된 자격증명 시 앱이 즉시 종료 |
| **3** | `ChatProvider` 인터페이스 + HCX/OpenAI 어댑터 + Registry | `providers/` 모듈 | `/v1/chat`이 provider 2개 모두에서 실제 응답 반환 |
| **4** | SSE 스트리밍 (`/v1/chat/stream`) + JSONL 로깅 + 글로벌 예외 핸들러 | 완성된 PoC | curl로 토큰 단위 응답 수신 확인, 로그 파일 누적 |
 
---
 
## 10. 검증 방법
 
### 10.1 단계별 smoke test
 
```bash
# 1단계
curl http://localhost:8000/health
 
# 3단계
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"provider": "hcx-003", "messages": [{"role": "user", "content": "안녕"}]}'
 
# 4단계 (스트리밍)
curl -N -X POST http://localhost:8000/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"provider": "hcx-003", "messages": [{"role": "user", "content": "안녕"}]}'
```
 
### 10.2 통합 체크리스트
 
- [ ] HCX provider 호출 시 Infisical에서 키를 가져온다 (앱 시작 로그로 확인).
- [ ] OpenAI provider는 `.env`의 키를 사용한다.
- [ ] Infisical 자격증명이 잘못되면 앱이 기동되지 않는다.
- [ ] JSONL 로그에 시크릿 값이 마스킹되어 있다.
- [ ] 멀티 turn 요청(`messages` 길이 ≥ 3)이 정상 동작한다.
- [ ] SSE 응답이 토큰 단위로 끊겨서 도착한다.
- [ ] 잘못된 `provider` 이름은 422 (Unprocessable Entity) 또는 통일된 에러로 반환된다.
