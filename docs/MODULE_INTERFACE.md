# 모듈 인터페이스 (파이프라인 단계 계약)

> 파이프라인 단계 모듈(`src/modules/`)이 **서로 어떻게 호출되고, 공유 데이터(`MasterSchema`)의 무엇을 읽고/쓰는지** 정의한다.
> 단계는 서로 직접 import 하지 않고 **하나의 공유 객체(`MasterSchema`)를 통해서만** 통신한다(파이프라인 + 공유 컨텍스트(Context Object) 패턴).
> 데이터 모델 상세: [`docs/PIPELINE_SCHEMA.md`](PIPELINE_SCHEMA.md) · [`src/schemas/runtime.py`](../src/schemas/runtime.py).

---

## 1. 호출 계약 (시그니처)

모든 파이프라인 단계는 **동일한 시그니처**를 따른다.

```python
async def <stage>(master_schema: MasterSchema) -> None:
    ...
```

`<stage>`는 실제 코드가 아니라 자리표시자(placeholder) 입니다. "여기에 단계 함수 이름을 넣어라"는 뜻.

| 규칙 | 내용 |
|---|---|
| 입출력 | `MasterSchema` 하나를 받아 **제자리 변경(in-place)**, 반환값 없음(`None`) |
| 실패 | 예외를 **raise** → `runner` 가 `StepEvent(error)` 로 변환하고 파이프라인 중단 |
| 단계 간 결합 | 단계끼리 직접 import 금지. 데이터는 `MasterSchema` 필드로만 주고받음 |
| 조립 | `src/pipeline/runner.py` 가 각 단계를 import 해 9단계로 순서 실행 (`_step` 이 `await fn(master_schema)` 호출) |
| 비동기 | `async def`. 동기 블로킹 작업(requests 등)은 `asyncio.to_thread` 로 위임 |

코드로 강제하려면 (선택) 다음 타입으로 명문화할 수 있다(현재 미적용):

```python
# src/pipeline/stage.py (제안)
from typing import Protocol, Awaitable, Callable
from src.schemas.runtime import MasterSchema

class PipelineStage(Protocol):
    async def __call__(self, master_schema: MasterSchema) -> None: ...

StageFn = Callable[[MasterSchema], Awaitable[None]]
```

---

## 2. 데이터 계약 (단계별 Reads / Writes)

`runner.run()` 실행 순서. **Reads = 전제(precondition)**, **Writes = 산출(postcondition)** — 둘 다 `MasterSchema` 기준.

| # | 단계 (함수) | Reads (전제) | Writes (산출) | 상태 |
|---|---|---|---|---|
| 1 | `load_article` | `content` | `article` | ✅ |
| 2 | `extract_statistical_claims` | `article.content` | `claims[]` (각 `claim_id` 부여) | ✅ (LLM) |
| 3 | `normalize_claim` | `claims[*].value.raw`, `claims[*].period_value.raw`, `article.published_at` | `claims[*].value.llm_value`, `claims[*].period_value.llm_value` | ✅ |
| 4 | `retrieve_kosis_candidates` | `claims[*].subject` | `analysis[]` = `kosis_search`(검색 로그·선정 tbl) + `candidates`(상위 N) + `kosis_query`(placeholder) | ✅ |
| 5 | `fetch_kosis_data` | `analysis[*].candidates`, `claims[*].(subject/population/period_value)` | `analysis[*].kosis_query`(조회 로그) + `analysis[*].evidence`(선정 셀) + `analysis[*].cell_attempts`(시도 로그) | ✅ |
| 6 | `calculate_metric` | `claims[*].value.llm_value`, `analysis[*].evidence` | 초기 verdict / mismatch_type | ⚠️ 더미(no-op) |
| 7 | `check_alignment` | `claims[]` + [6] 결과 | 모호 케이스 재판정 보정 | ⚠️ 더미(no-op) |
| 8 | `decide_verdict` | `claims[]` + [6][7] 결과 | `verifications` = `summary` + `claim_results[]`(각 `evidence[]` 포함) | ⚠️ 더미(UNVERIFIED 고정) |
| 9 | `generate_explanation` | `verifications`, `claims[]` | `verifications.claim_results[*].explanation` | ✅ |

> ⚠️ 상태 = 인터페이스(계약)는 정해졌으나 본문이 아직 더미. 계약을 깨지 않고 내부만 구현하면 됨.

---

## 3. 공유 스키마가 채워지는 흐름

단계가 진행되며 `MasterSchema` 의 상위 필드가 순차로 채워진다(진행 중에는 미완성 허용 = Optional).

```
content ──[1]──▶ article ──[2]──▶ claims[] ──[3]─▶ (claims 값 정규화)
        ──[4]──▶ analysis[](검색·후보) ──[5]─▶ analysis[*].evidence(공식 수치)
        ──[6][7][8]──▶ verifications(판정) ──[9]─▶ claim_results[*].explanation
```

`MasterSchema` 구조: `content`(입력) · `article` · `claims[]` · `analysis[]` · `verifications`.
`ClaimAnalysis`: `claim_id` · `kosis_search` · `candidates[]` · `cell_attempts[]` · `kosis_query` · `evidence`.

---

## 4. 공통 규칙 (계약 부속)

- **누락값은 `None`**, 빈 문자열 `""` 금지 (`docs/PIPELINE_SCHEMA.md`).
- **검증·비교는 항상 `LLM_Metrics`(=`llm_value`)** 사용. `raw`(원문 표기)는 표시·근거용.
- **LLM 호출은 반드시 `src/llm/llm_caller.py(LlmCaller)` 경유**, 파라미터는 `model_presets` 에서만 (`CLAUDE.md`).
- 식별자 형식(`article_id` / `claim_id` / `evidence_id`)·날짜 규칙 → `docs/PIPELINE_SCHEMA.md`.

---

## 5. 선형 흐름 밖 / 미연결 모듈 (주의)

| 모듈 | 비고 |
|---|---|
| `create_hitl_task`, `save_hitl_feedback` | HITL — 선형 파이프라인 **밖**(runner 9단계에 없음). 시그니처는 동일 계약 준수 |
| `preprocess_article`, `rank_evidence` | 현재 runner 체인에 **미연결**. `rank_evidence` 는 인자명이 `record` 로 관례(`master_schema`)와 불일치 → 통일 필요 |

---

## 참고

- 런타임/저장 모델 상세: [`docs/PIPELINE_SCHEMA.md`](PIPELINE_SCHEMA.md)
- 스키마 코드: [`src/schemas/runtime.py`](../src/schemas/runtime.py)
- 외부(프론트↔백) API 계약: [`docs/WEB_API_CONTRACT.md`](WEB_API_CONTRACT.md)
- 이벤트 스트리밍: [`src/pipeline/events.py`](../src/pipeline/events.py)