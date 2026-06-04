# 기술 스택 (Tech Stack)

> fake-news-detect — 기사의 **통계 수치 주장**을 국가통계와 대조해 진위(T/F/판단불가)를 검증하는 시스템.

## 한 줄 요약
Python · FastAPI 비동기 API에서 **멀티 LLM + 임베딩 기반 검색 + 외부 통계 API**를 조합해 수치 주장을 검증하고, 진행 상황을 **SSE로 단계별 스트리밍**한다. LLM 호출은 **Langfuse**로 추적한다.

---

## 기술 스택 (핵심)

| 스택 | 용도 |
|---|---|
| **Python 3.11** | 구현 언어 |
| **FastAPI** (ASGI: uvicorn) | API 서버. **SSE**(sse-starlette)로 파이프라인 단계 진행을 실시간 스트리밍 |
| **Pydantic v2** | 마스터 스키마(Single Source of Truth) 정의·검증. Article/Claims/Analysis 중첩 구조 |
| **멀티 LLM 프로바이더** | **HyperCLOVA X(주력)** · OpenAI · Gemini · Claude를 단일 `LlmCaller`로 추상화 (function calling / structured output / thinking 가드 포함) |
| **CLOVA Studio 임베딩** | 통계표 메타데이터·검색 키워드 임베딩 (`clir-emb-dolphin`) |
| **PostgreSQL + pgvector** | 임베딩 벡터 스토어 (docker-compose로 구성. *앱 코드 연동은 진행 중*) |
| **Langfuse** | LLM 호출 트레이싱·관측 |
| **Docker / docker-compose** | 컨테이너화 및 배포(VM) |

---

## 면접 대비 포인트
- **왜 SSE인가** — 검증이 9단계로 수 초가 걸리므로, 단계별 진행을 실시간으로 push. 생성(파이프라인)과 전송(SSE)을 분리해 runner는 전송 방식을 모른다.
- **왜 멀티 LLM 추상화인가** — 태스크별 최적 모델 선택 + 벤더 종속 회피. provider별 기능 차이(structured output·thinking 등)를 가드로 통일.
- **왜 Pydantic SSOT인가** — 모듈 간 계약을 코드 한 곳(마스터 스키마)에서 강제하고, 개발자 간 교환은 JSON으로.
- **왜 pgvector인가** — KOSIS 통계표 메타데이터를 임베딩해 의미 기반 후보 검색(RAG)에 쓰기 위한 벡터 스토어.
