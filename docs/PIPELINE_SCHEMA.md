# Pipeline Storage & Conventions Schema

> **대상 독자**: 백엔드 개발자. 이 문서는 **저장 모델(DB)·식별자·공통 규약**만 다룬다.
> 필드 단위 명세(타입·nullable·구조)는 더 이상 여기 두지 않는다 — **드리프트 방지**를 위해 아래로 위임:
> - **필드 정의의 SSOT** = `src/schemas/runtime.py`(Pydantic `MasterSchema` 등). 형태의 진실은 코드 한 곳.
> - **단계별 입출력** = `docs/PIPELINE_STAGES_IO.md` (1~10단계 read/write 경로).
> - **외부 API 응답** = `docs/WEB_API_CONTRACT.md` (프론트 계약).

---

## 1. 런타임 → 저장 모델

### 1.1 런타임 최상위 구조 (`MasterSchema`)

런타임 중에는 아래 **4개 최상위 필드**를 하나의 `MasterSchema` 로 묶어 10단계 끝까지 흐른다(직접 흐름, option 2). 진행 중 미완성이 합법이라 상위 필드는 Optional.

| 런타임 경로 | 타입 | 카디널리티 | 채우는 단계 | 저장 대상(설계) |
|---|---|---|---|---|
| `article` | `Article \| None` | 1 | [1] | `articles` |
| `claims` | `list[Claim]` | 0~N | [2]·[3] | `claims` |
| `analysis` | `list[ClaimAnalysis]` | 0~N (claim과 1:1, `claim_id` 조인) | [4]·[5] | `analyses` |
| `verifications` | `Verifications \| None` | 1 (안에 `claim_results[]` = claim당 1) | [7]~[10] | `verifications` |
| `content` | `str \| None` | 1 | 입력 | **저장 안 함** (`exclude=True` — `model_dump()` 제외) |

이전 명세 대비 바뀐 핵심:
- **검증 결과 위치 이동**: 옛 `analysis[*].verification`(분석 안) → 별도 최상위 **`verifications` = `{summary, claim_results[]}`**. 즉 저장 스키마가 **3개(article/claim/analysis) → 4개**로 늘었다.
- **`evidence` 카디널리티**: 옛 `analysis[*].evidence[]`(배열) → **`analysis[*].evidence: Evidence | None`(선정 셀 단일)**. 저장도 1:1.
- **신규 중첩 구조**: `analysis[*].candidates[]`(후보 풀)·`cell_attempts[]`(조회 시도 로그), `claim_results[*].metric`(`MetricResult`, 수치비교+정합성). → §1.3 영속화 정책 참고.

### 1.2 저장 구현 상태 — **현재 미구현(설계만)**

- **실제 DB 테이블은 `users`(auth)만** 존재(`src/auth/models.py`, SQLAlchemy). 파이프라인 산출물용 `articles`/`claims`/`analyses`/`verifications` 는 **아직 없다**.
- 파이프라인 결과는 현재 **DB에 저장하지 않고**, 끝에서 `ResultEvent.master_schema.model_dump()` → **SSE `result` 이벤트(JSON)** 로만 내보낸다(`src/pipeline/runner.py`). 소비·표시는 프론트/`src/api/result_view.py` 몫.
- 따라서 아래 테이블 매핑·식별자 포맷은 **목표 설계**이며, 영속화 작업 시 이 문서를 계약으로 삼는다.

### 1.3 테이블 매핑 (설계)

`claim_id` 를 공유 FK로 `claims`·`analyses`·`claim_results` 를 잇는다.

| 테이블 | 1행 단위 | 런타임 출처 | 비고 |
|---|---|---|---|
| `articles` | 기사 1건 | `article` | |
| `claims` | 주장 1건 | `claims[*]` | `value`/`period_value`/`compare_period_value` = `ValueSlot`(§3.3), `compare_conquer` = `ComparisonSpec` |
| `analyses` | 주장 1건의 KOSIS 분석 | `analysis[*]` | `kosis_search`·`kosis_query`·선정 `evidence`(1:1) |
| `verifications` | 주장 1건의 판정 | `verifications.claim_results[*]` | `verdict`·`mismatch_type`·`metric`·`explanation` 등 |
| (요약) | 기사 1건 | `verifications.summary` | `overall_verdict`·`average_confidence` → `articles` 컬럼으로 흡수 또는 별도 1행 |

**디버깅·풀 데이터 영속화 정책(미결)**: `analysis[*].candidates[]`(후보 10개)·`cell_attempts[]`(표별 조회 시도)는 표시·디버깅용이다. (a) JSON 컬럼으로 통째 보관 / (b) 별도 테이블 정규화 / (c) 영속화 제외 중 결정 필요.

---

## 2. 식별자 규칙

### 2.1 목표 포맷

| 식별자 | 포맷 | 예시 |
|---|---|---|
| `article_id` | `{source}_{YYYYMMDD}_{hash4}` | `chosun_20250314_a3f2` |
| `claim_id` | `{article_id}_c{NN}` | `chosun_20250314_a3f2_c01` |
| `evidence_id` | `ev_{claim_id}_{NN}` | `ev_chosun_20250314_a3f2_c01_01` |

`hash4`: 본문 또는 URL의 SHA-256 앞 4자리 16진수. `NN`: 2자리 순번(01~).

### 2.2 현재 구현 — **placeholder (목표 포맷 미적용)**

| 식별자 | 현재 코드값 | 위치 |
|---|---|---|
| `article_id` | 고정 `"art-0001"` | `src/modules/load_article.py` |
| `claim_id` | `f"clm-{idx:04d}"` → `"clm-0001"` | `src/modules/extract_statistical_claims.py` |
| `evidence_id` | **미설정(None)** | `src/modules/fetch_kosis_data.py`(`_to_evidence` 가 안 채움) |

→ 영속화 전 §2.1 포맷으로 교체 필요(`source`·발행일·hash4 배선). 단일 기사 검증 흐름에선 고정값으로도 동작.

---

## 3. 공통 규약

### 3.1 날짜·시각
- 날짜만: ISO 8601 `YYYY-MM-DD` (예: `2025-03-14`).
- 타임스탬프: ISO 8601 + **타임존 필수** (예: `2026-05-11T09:12:03Z`, `…+09:00`). `evidence.retrieved_at` 이 이 형식(UTC, `timespec="seconds"`).

### 3.2 누락값
- 모르면 `null`(Python `None`). 빈 문자열 `""` 사용 지양. KOSIS 미조회 필드(`evidence.value`/`kosis_*`/`url` 등)는 더미값 금지·`None` 유지.

### 3.3 `ValueSlot` (옛 "Originalvalue")
`Claim` 의 `value`·`period_value`·`compare_period_value` 공통 3-필드. 직렬화 키는 alias(`populate_by_name=True`).

| 코드 필드 | JSON alias | 타입 | 설명 |
|---|---|---|---|
| `raw` | `Original_table` | string | 본문 표기 그대로 (`"약 23만"`, `"전년"`) |
| `llm_value` | `LLM_Metrics` | string | 정규화 표준 표현 (`"230000"`, `"2023"`) — **비교·검증은 항상 이 값** |
| `is_inferred` | `Inferred` | bool | 본문 미명시·문맥 추론이면 `true` |

### 3.4 enum 코드값 (한글 라벨 아님)
저장·교환은 **코드값**으로 한다. 한글 라벨 매핑은 프론트(`web/.../format.ts`) 몫.

| enum | 코드값 |
|---|---|
| `Verdict` | `T`(일치)·`F`(불일치=확정 가짜)·`M`(오도/왜곡)·`N`(NEI) |
| `ClaimType` | `absolute`·`change_rate`·`ratio`·`distribution`·`comparison`·`metaphoric`·`verifiable`·`none` |
| `MismatchType` | `magnitude`·`rounding`·`direction`·`unit`·`period`·`population`·`subject`·`aggregation` |
| `PeriodType` | `Y`·`M`·`Q`·`S`·`D` |

---

## 4. 런타임 아키텍처 (요약)

상세 설계 이력이 아니라 저장·직렬화에 직접 닿는 부분만.

- **데이터(스키마) ↔ 동작(로직) 분리**: 스키마 `src/schemas/`, 단계 동작 `src/modules/`(단계당 1파일, `(master_schema) -> None` 제자리 변경).
- **`MasterSchema` 직접 흐름**(별도 ctx 없음). 실패는 `raise` → runner 가 `StepEvent(error)` 로 변환·중단.
- **결과 직렬화**: 파이프라인 끝 `ResultEvent.master_schema.model_dump()` → SSE `result`(JSON). `content`는 `exclude`라 빠짐. 별도 완성 게이트 없음(전부 Optional) → 경계(DB/API)에서 필요 시 `None` 가드.
- **DTO는 시스템 경계(HTTP)에만**(`src/api/`).

---

## 5. 미결 / 할 일

- **영속화 미구현**: `articles`/`claims`/`analyses`/`verifications` 테이블·저장 로직 부재(현재 SSE JSON 전송만). §1.3 매핑으로 구축.
- **식별자 배선**: §2.2 placeholder → §2.1 목표 포맷(`source`·발행일·hash4) 교체.
- **풀·디버깅 데이터 영속화 정책**: `candidates[]`/`cell_attempts[]` 보관 방식 결정(§1.3).
- **summary 저장 위치**: `verifications.summary` → `articles` 흡수 vs 별도 행.
- **HITL**: `save_hitl_feedback` 미구현(`NotImplementedError`) — `verdict_human`/`verdict_human_note` 반영·저장 경로 필요.
- **`confidence`/`verdict_human`/`llm_model`**: [9] `decide_verdict` 가 아직 `0.0`/미산출(TODO) — 저장 전 채움.
