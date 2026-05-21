# LLM Chat API (PoC)

기존 Chat Client(`src/llm/client.py`)를 FastAPI 로 래핑한 얇은 어댑터.
`src/API_rule.md` 명세 기반. 기존 파일은 일절 수정하지 않음.

## API_rule.md 와 다른 점 (의도된 조정)

| 항목 | 명세 | 실제 구현 | 이유 |
|---|---|---|---|
| HCX 시크릿 | Infisical **Python SDK** + `secrets/` 모듈 | Infisical **CLI** env 주입 (`uv run x`) | 프로젝트가 `scripts/run.py`(`infisical run -- uv run`)로 이미 표준화. SDK 재구현은 중복·상충 |
| 키 이름 | `HCX_API_KEY` | `CLOVASTUDIO_API_KEY` → `ChatClient(api_key=...)` 로 전달 | 기존 `client.py`(수정 금지)는 `HCX_API_KEY` 를 읽음. config 가 이름 차이 흡수 |
| `/v1/chat/stream` | SSE 스트리밍 | **생략** | 기존 동기 `ChatClient` 에 stream 메서드 없음 + 수정 금지 (사용자 결정) |
| OpenAI provider | registry 에 포함 | 미포함 (HCX 만) | 프로젝트는 HCX 전용. registry 1줄로 확장 가능 |

## 설치

```bash
# 프로젝트 루트에서
uv pip install -r src/api/requirements.txt
```

## 기동

```bash
bash src/api/run.sh
# 또는 프로젝트 루트에서 직접:
uv run x uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

`uv run x` 가 `infisical run -- uv run` 으로 풀려 `CLOVASTUDIO_API_KEY` 가
주입된다. 키가 주입되지 않으면 **앱이 기동되지 않는다**(fail-fast).

## 엔드포인트

| 메서드 | 경로 | 용도 |
|---|---|---|
| `GET`  | `/health` | liveness |
| `GET`  | `/v1/providers` | provider 목록 |
| `POST` | `/v1/chat` | 단일/멀티턴 (stateless) |

provider 이름: `hcx-dash-001`, `hcx-003`, `hcx-005`, `hcx-007`.

## smoke test

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"provider": "hcx-005", "messages": [{"role": "user", "content": "안녕"}]}'
```

## 로깅

요청·응답이 `LOG_DIR`(기본 `./logs`)에 날짜별 JSONL 로 누적된다. `nv-` 키
패턴과 시크릿 키 이름은 마스킹된다. `logs/` 는 `.gitignore` 대상.
