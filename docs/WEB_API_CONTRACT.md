# 웹 UI ↔ 백엔드 API 계약서 (`POST /verify`)

> **대상 독자**:
> - **백엔드 개발자** — §1 요청 / §2 응답 스키마 / **§3 변환 규칙 (Pipeline → API)** / §4 에러 / §6 체크리스트
> - **프론트엔드 개발자** — §2 응답 스키마 / §4 에러 / §5 응답 예시
>
> **목적**: 프론트(`web/`)가 화면에 표시하기 위해 필요로 하는 데이터의 형식·의미·필수여부를 백엔드 구현 기준으로 명세한다.
> **단일 진실 원천(SSOT)**: `web/src/lib/api/schema.ts` (zod 스키마). 본 문서와 코드 스키마가 불일치할 경우 코드 스키마가 우선하며, 본 문서는 즉시 갱신한다.
> **버전**: v1 (POC) · 마지막 갱신: 2026-05-14

---

## 0. 개요

- 프론트는 단일 엔드포인트 `POST /verify` 만 호출한다.
- 응답에는 **결과 화면에 필요한 모든 정보가 한 번에** 포함된다 (스트리밍/SSE/폴링 없음).
- 응답은 클라이언트에서 **zod로 strict 검증**되며, 필드 누락·타입 불일치 시 사용자에게 "응답 형식이 예상과 다릅니다" 에러로 즉시 실패한다.
- 로딩 중 9단계 progress bar는 클라이언트 측 시간 기반 시뮬레이션이며, 응답이 도착하면 `pipeline[]` 으로 최종 상태가 덮어쓰여진다 → 백엔드는 **각 단계의 실제 결과 상태**를 정확히 채워줘야 한다.
- **백엔드 책임 범위**: `result` 화면용 데이터만 책임진다. `idle`(랜딩) / `loading` / `error` 화면의 모든 텍스트·배지·예시(헤로 헤드라인, 4가지 판정 예시, 작동 방식 카드 등)는 프론트 하드코딩이며 서버 데이터를 일절 사용하지 않는다.
- 백엔드는 내부 모델(`docs/PIPELINE_SCHEMA.md`)을 **§3 변환 규칙**대로 평탄화해서 응답한다.

---

## 1. 요청 (Request)

### 1.1 엔드포인트
```
POST {VITE_API_BASE_URL}/verify
Content-Type: application/json
```
- 기본 base URL: `http://localhost:8000`
- 클라이언트 타임아웃: **90초** (초과 시 HTTP 408로 처리됨)

### 1.2 요청 바디
| 필드 | 타입 | 필수 | 검증 | 설명 |
|------|------|:---:|------|------|
| `url` | string | ✅ | 유효한 URL 형식 (`zod .url()`) | 검증 대상 뉴스 기사 URL |

```json
{ "url": "https://www.chosun.com/economy/.../2024/01/15/ABCDE/" }
```

---

## 2. 응답 (Response) — `VerifyResponse`

성공 시 `200 OK` + 아래 스키마 준수.

### 2.1 최상위 필드 요약

| # | 필드 | 타입 | nullable | UI 사용처 | 비고 |
|---|------|------|:---:|----------|------|
| 1 | `request_id` | string | ❌ | (미표시) | 디버깅/트레이싱용. 로그 상관관계 |
| 2 | `article` | object | ❌ | 결과 화면 상단 바 | §2.2 |
| 3 | `claim` | object | ❌ | `ClaimCard` (대표 주장) | §2.3 |
| 4 | `all_claims` | object[] | ❌ (빈 배열 허용) | **현재 미사용** (향후 다중주장 확장) | 각 원소는 `claim`과 동일 스키마 |
| 5 | `verdict` | enum | ❌ | `VerdictBadge` 상단 대형 라벨 | §2.6 |
| 6 | `confidence` | number | ❌ | `VerdictBadge` 신뢰도 게이지 | 0.0 ~ 1.0, `×100`해서 정수%로 표시 |
| 7 | `evidence` | object \| null | ✅ | `KosisTableCard` (null이면 "매칭 없음" 안내) | §2.4 |
| 8 | `comparison` | object \| null | ✅ | `NumericComparison` 섹션 (null이면 섹션 미렌더) | §2.5 |
| 9 | `explanation` | string | ❌ | `ExplanationPanel` 자연어 분석 설명 | 슬롯-필 결과를 한 문단으로 |
| 10 | `pipeline` | object[] | ❌ (정확히 9개) | `PipelineProgress` 단계별 노드 | §2.7 |

### 2.2 `article` — 기사 메타
| 필드 | 타입 | nullable | UI 표시 |
|------|------|:---:|---------|
| `url` | string (URL) | ❌ | 상단 바 모노스페이스, 1줄 truncate. 요청 URL을 그대로 반환해도 됨 |
| `title` | string \| null | ✅ | 상단 바 굵은 글씨 (null이면 미표시) |
| `published_at` | string \| null | ✅ | "YYYY년 M월 D일 발행" 형식으로 표시. 프론트가 `new Date(value).toLocaleDateString('ko-KR', ...)`로 변환하므로 **`Date.parse()` 가능한 문자열(ISO 8601 권장)** 이어야 함. ⚠️ zod 검증은 단순 `z.string().nullable()`이라 통과하지만, 파싱 불가 문자열이면 **화면에 "Invalid Date" 가 표시**된다 |

### 2.3 `claim` — 구조화된 대표 주장 (8-슬롯 + 메타)
사용처: `web/src/components/claim/ClaimCard.tsx` — 인용 블록 + 슬롯 테이블로 렌더.

| 필드 | 타입 | nullable | 화면 라벨 | 설명 |
|------|------|:---:|----------|------|
| `claim_id` | string | ❌ | (내부 식별자) | 단일 응답 내 유일 |
| `raw_text` | string | ❌ | 인용 블록 `"..."` | 원문에서 추출한 주장 문장 그대로 |
| `claim_type` | enum | ❌ | "주장유형" + 우상단 뱃지 | 아래 enum 표 참조 |
| `year` | int \| null | ✅ | "년도" | 4자리 연도 |
| `compare_year` | int \| null | ✅ | "비교년도" | 비교 기준 연도 (없으면 null) |
| `item` | string | ❌ | "항목" | 통계 항목명 (예: "청년 실업률") |
| `value` | number \| null | ✅ | "수치" | 본문에 명시된 숫자값. 없으면 null (정성주장 등) |
| `unit` | string | ❌ | "수치" 뒤 단위 | 빈 문자열 허용 |
| `population` | string \| null | ✅ | "모집단" | 예: "15~29세", "전국" |
| `aggregation` | string \| null | ✅ | "집계방식" | 예: "연간 평균", "월간" |
| `cited_source` | string \| null | ✅ | "인용출처" | 기사 내 인용 표기 (예: "통계청 고용동향") |

#### `claim_type` enum
한글 라벨은 프론트(`web/src/lib/format.ts` `CLAIM_TYPE_LABELS`)에서 매핑됨. 백엔드는 **enum 코드만 정확히** 보내면 된다.

| 코드 | 한글 라벨 | 의미 |
|------|----------|------|
| `absolute` | 절대값 | 단일 시점의 절대값 |
| `change_rate` | 증감률 | 전년대비 증감률 등 |
| `ratio` | 비율 | A/B 비율 |
| `distribution` | 분포 | 구성비/점유율 |
| `comparison` | 비교 | 그룹간 비교 |
| `metaphoric` | 정성/추상 | 정성·비유적 표현 |

### 2.4 `evidence` — KOSIS 통계표 출처 (nullable)
`null` 인 경우: 매칭 통계표를 찾지 못한 케이스 (대개 `verdict='N'`). 프론트는 자리표시자("매칭 통계표 없음")로 대체.

사용처: `web/src/components/evidence/KosisTableCard.tsx`

| 필드 | 타입 | nullable | 화면 표시 | 설명 |
|------|------|:---:|----------|------|
| `table_id` | string | ❌ | 모노스페이스 chip | 예: `DT_1DA7001S` |
| `org_id` | string | ❌ | (직접 미표시) | 예: `101` (통계청). URL 구성에 사용될 수 있음 |
| `table_name` | string | ❌ | 카드 제목 | 예: "고용동향 - 실업률 (연령별)" |
| `table_url` | string (URL) | ❌ | "KOSIS에서 보기" 외부 링크 | `https://kosis.kr/...` |
| `period` | string | ❌ | "기준연도" | 자유 형식 문자열 (예: `"2023"`, `"2023.Q4"`) |
| `classification` | `Record<string,string>` | ❌ | grid의 각 칸: 라벨 "분류" + value 텍스트 | 빈 객체 `{}` 허용. **키(`C1` 등)는 화면에 표시되지 않고 React key로만 사용됨** — 라벨은 항상 "분류"가 반복 표시되므로, 백엔드는 **사용자에게 의미 있는 값(value)** 만 잘 채우면 된다. 예: `{ "C1": "청년층 (15~29세)", "C2": "남자" }` → 화면 "분류: 청년층 (15~29세) / 분류: 남자" |
| `official_value` | number | ❌ | 강조 영역 대형 숫자 | KOSIS 공식 수치 |
| `official_unit` | string | ❌ | 위 숫자 옆 단위 | 예: `"%"`, `"명"` |
| `retrieved_at` | string (ISO 8601 datetime) | ❌ | "조회일: ..." | 예: `"2024-01-15T09:05:00Z"`. zod `.datetime()` 통과 필요 |

### 2.5 `comparison` — 수치 비교 결과 (nullable)
`null` 인 경우: 비교 자체가 불가능했던 케이스 (정성주장·전망치·증거 없음 등). 프론트는 섹션 자체를 렌더하지 않음.

사용처: `web/src/components/evidence/NumericComparison.tsx`

| 필드 | 타입 | nullable | 화면 표시 | 설명 |
|------|------|:---:|----------|------|
| `article_value` | number \| null | ✅ | 좌측 "기사 수치" (null이면 `—`) | 기사에서 추출된 값. `claim.value`와 일치하는 것이 일반적 |
| `official_value` | number | ❌ | 우측 "KOSIS 공식" | `evidence.official_value`와 동일해야 함 |
| `unit` | string | ❌ | 양쪽 카드 단위 | 단위 정렬 후의 최종 단위 |
| `abs_diff` | number | ❌ | "차이: ..." | `\|article_value - official_value\|`. `article_value`가 null이어도 백엔드는 계산값을 반환 (불가능하면 `0`) |
| `rel_diff_pct` | number | ❌ | "오차율: N%" (소수 1자리 표시) | 백분율 그대로 (예: `31.9`는 31.9%) |
| `tolerance_pct` | number | ❌ | "(허용 ±N%)" | **소수 (예: `0.05`는 5%)** — 프론트가 `×100`해서 표시 |
| `within_tolerance` | boolean | ❌ | ✓/✕ + 카드 색상(녹/적) 토글 | 판정 핵심 시그널 |

**주의**: `tolerance_pct`만 0~1 소수, `rel_diff_pct`는 백분율 숫자. 단위가 섞이지 않도록 주의.

### 2.6 `verdict` enum + `confidence`
사용처: `web/src/components/verdict/VerdictBadge.tsx` (+ `web/src/lib/verdict.ts`의 메타 매핑)

| `verdict` | 코드명 | 라벨 | 설명 (프론트 고정 문구) |
|:---:|------|------|------------------------|
| `T` | TRUE | 진짜 | 기사의 수치가 공식 통계와 일치합니다 |
| `F` | FALSE | 가짜 | 기사의 수치가 공식 통계와 불일치합니다 |
| `M` | NEEDS_REVIEW | 모호 | 정량적 비교가 어렵거나 판정이 불확실합니다 |
| `N` | NO_EVIDENCE | 판단불가 | 대응하는 KOSIS 통계를 찾을 수 없습니다 |

`confidence`:
- **타입**: `number`, 범위 `[0.0, 1.0]` (zod `min(0).max(1)`)
- **표시**: `Math.round(confidence * 100)` → "92%"
- 0인 경우(`N` 판정 등)도 0%로 정상 표시됨

### 2.7 `pipeline[]` — 9단계 실행 내역
사용처:
- 로딩 화면: 클라이언트가 자체 타이머로 진행 표시 (응답 대기 중)
- 결과 화면: `ResultLayout` 하단 "파이프라인 실행 내역"에서 **응답값으로 최종 상태 렌더**

**고정 길이 9개**. 각 원소 스키마:

| 필드 | 타입 | nullable | 설명 |
|------|------|:---:|------|
| `step` | int (1~9) | ❌ | 단계 번호 (배열 순서대로 1→9) |
| `name` | string | ❌ | 단계명. 프론트는 자체 `STEP_NAMES` 상수를 사용하므로 **현재 화면에 표시되지는 않지만**, 로그·디버그용으로 정확히 채울 것 |
| `status` | enum | ❌ | `'pending' \| 'running' \| 'done' \| 'skipped' \| 'error'` |
| `duration_ms` | int \| null | ✅ | 단계 소요 시간(ms). `skipped`/실행 안 함이면 null. **현재 UI에 미렌더이나 향후 확장용** |

#### 9단계 표준 명세 (`name` 권장값 — `web/src/lib/api/mock.ts` 기준)
| step | name |
|:---:|------|
| 1 | 기사 내용 추출 |
| 2 | 주장 탐지 |
| 3 | 주장 분류 |
| 4 | 주장 구조화 (8-슬롯) |
| 5 | KOSIS 카탈로그 필터링 |
| 6 | 임베딩 검색 (Top-50) |
| 7 | 재순위화 (Top-5) |
| 8 | RAG 추론 (Top-1) |
| 9 | KOSIS API + 수치 비교 |

#### `status` 사용 규칙
- 정상 완료된 단계: `done`
- 본 단계에서 검증 중단(다음 단계 의미 없음): 해당 단계 `error`, 이후 단계들은 모두 `skipped` (`duration_ms: null`)
- 의도적으로 건너뛴 단계 (예: 전망치라 비교 생략): `skipped`
- `pending`/`running`은 응답에 포함되지 않아야 함 (응답은 항상 종료 상태)

---

## 3. Pipeline → API 변환 규칙

백엔드는 내부 모델(`docs/PIPELINE_SCHEMA.md`)에서 응답을 만들 때 본 절을 따른다. 출처 표기는 `Article.title`, `Claim.sentence`처럼 Pipeline 측 필드명을 사용.

### 3.1 최상위 필드 매핑
| Web API 필드 | Pipeline 출처 | 변환 |
|--------------|--------------|------|
| `request_id` | (신규 생성) | UUID 또는 트레이스 ID |
| `article.url` | (요청에서 echo) | 입력 URL 그대로 |
| `article.title` | `Article.title` | 그대로 |
| `article.published_at` | `Article.published_at` | ISO 형식 그대로 |
| `claim` | `claims[]` 중 1건 선정 | §3.2, §3.3 |
| `all_claims` | `claims[]` 전체 | 각 원소에 §3.3 변환 |
| `verdict` | `analysis[대표].verification.verdict` | §3.4 한글 → 코드 |
| `confidence` | `analysis[대표].verification.confidence` | 그대로 |
| `evidence` | `analysis[대표].evidence[]` 중 1건 선정 | §3.5 |
| `comparison` | (Numeric Layer 계산) | §3.6 |
| `explanation` | `analysis[대표].verification.explanation` | 그대로 |
| `pipeline` | (단계별 메타 집계) | §3.7 |

### 3.2 다주장 → 단일 대표 주장 선정
**규칙 TBD.** 잠정: 검증 가능한 `claim_type` 중 `analysis.verification.confidence`가 가장 높은 claim. 동률 시 `claims[]` 등장 순서.

### 3.3 Claim 필드 변환 (Pipeline Claim → API ClaimCard, §2.3)
| API 필드 | Pipeline 출처 | 비고 |
|----------|--------------|------|
| `claim_id` | `claim_id` | 그대로 |
| `raw_text` | `sentence` | rename |
| `claim_type` | `claim_type` 한글 | §3.4 영문 enum 매핑 |
| `year` | `period_value.LLM_Metrics` | int 변환 (실패 시 null) |
| `compare_year` | `compare_period_value.LLM_Metrics` | int 변환 (`compare_period_value`가 null이면 null) |
| `item` | `subject` | rename |
| `value` | `value.LLM_Metrics` | number 변환 (실패 시 null) |
| `unit` | `unit` | 그대로 |
| `population` | `population` | 빈 값이면 null |
| `aggregation` | `aggregation` | 그대로 |
| `cited_source` | `cited_source` | 빈 값이면 null |

### 3.4 Enum 매핑

**`verdict`** (확정):
| Pipeline | Web API |
|----------|:---:|
| 일치 | `T` |
| 불일치 | `F` |
| 판단불가 | `N` |
| 모호 | `M` |

**`claim_type`** (**TBD** — Pipeline 측 enum 미확정):
| Pipeline | Web API |
|----------|---------|
| 규모 | `absolute` (잠정) |
| TBD | `change_rate` |
| TBD | `ratio` |
| TBD | `distribution` |
| TBD | `comparison` |
| TBD | `metaphoric` |

### 3.5 다증거 → 단일 대표 증거 선정 + Evidence 필드 매핑
**선정 규칙 TBD.** 잠정 우선순위:
1. `claim.period_value.LLM_Metrics`와 일치하는 `period_value`를 가진 evidence
2. 동률 시 `last_updated` 최신
3. 그래도 동률이면 `evidence_id` 사전순 첫번째

evidence가 0건이면 `evidence: null`.

**Evidence 필드 매핑** (Pipeline evidence → API §2.4):
| API 필드 | Pipeline 출처 |
|----------|--------------|
| `table_id` | `kosis_tbl_id` |
| `org_id` | `kosis_org_id` |
| `table_name` | `kosis_tbl_name` |
| `table_url` | `kosis_url` |
| `period` | `period_value` |
| `classification` | `classification` |
| `official_value` | `value` |
| `official_unit` | `unit` |
| `retrieved_at` | `retrieved_at` (**타임존 필수**) |

### 3.6 `comparison` 계산 (Numeric Layer)
대표 evidence가 있을 때만 계산.

| API 필드 | 계산 |
|----------|------|
| `article_value` | `parseFloat(claim.value.LLM_Metrics)` (실패 시 null) |
| `official_value` | `evidence.value` |
| `unit` | `evidence.unit` (단위 정렬 후) |
| `abs_diff` | `\|article_value − official_value\|` (계산 불가 시 `0`) |
| `rel_diff_pct` | `abs_diff / official_value × 100` (백분율 숫자) |
| `tolerance_pct` | 데이터 기반 (소수) — **산출 규칙 TBD** (CLAUDE.md에 "유효숫자 기반"으로 명시) |
| `within_tolerance` | `rel_diff_pct / 100 ≤ tolerance_pct` |

`verdict ∈ {판단불가, 모호}` 또는 evidence 0건 → `comparison: null`.

### 3.7 `pipeline[]` 9단계 구성
외부 표시용 고정 구조. 런타임 메타에서 다음과 같이 집계:

| step | name | status 출처 | duration_ms 출처 |
|:---:|------|-------------|----------------|
| 1 | 기사 내용 추출 | TBD | TBD |
| 2 | 주장 탐지 | TBD | TBD |
| 3 | 주장 분류 | TBD | TBD |
| 4 | 주장 구조화 (8-슬롯) | TBD | TBD |
| 5 | KOSIS 카탈로그 필터링 | TBD | TBD |
| 6 | 임베딩 검색 (Top-50) | TBD | TBD |
| 7 | 재순위화 (Top-5) | TBD | TBD |
| 8 | RAG 추론 (Top-1) | TBD | TBD |
| 9 | KOSIS API + 수치 비교 | `analysis.kosis_query.success` | `analysis.kosis_query.duration_ms` |

상태 enum (`done`/`skipped`/`error`)과 중단 시 패턴은 §2.7 참조.

### 3.8 응답에서 드롭되는 Pipeline 필드
응답에 포함하지 않음 (내부/디버그/저장 전용):
- **Article**: `article_id`, `content`, `source`
- **Claim**: `article_id`, Originalvalue의 `Original_table` · `Inferred` (`LLM_Metrics`만 노출)
- **Analysis**: `kosis_search` / `kosis_query` 전체 (단, `success` · `duration_ms`는 §3.7에서 활용), 비대표 evidence들
- **Evidence**: `evidence_id`, `claim_id`, `source`, `kosis_item_id`, `last_updated`
- **Verification**: `mismatch_type`, `claim_value`, `kosis_value`, `llm_model`

---

## 4. 에러 응답

프론트의 에러 처리: `web/src/lib/api/client.ts` (`ApiError`)

| HTTP 상태 | 클라이언트 동작 |
|:---:|---------------|
| `2xx` 이면서 스키마 불일치 | `"응답 형식이 예상과 다릅니다. (백엔드 스키마 확인 필요)"` 에러 화면 |
| `4xx`, `5xx` | 응답 본문 텍스트를 그대로 에러 메시지로 표시 |
| 90초 타임아웃 | `"검증 시간이 초과되었습니다 (90초). 잠시 후 다시 시도하세요."` |

**권장 에러 응답 형식** (강제 아님, 표시용 텍스트면 됨):
```
HTTP/1.1 4xx
Content-Type: text/plain; charset=utf-8

사용자에게 보여줄 한 줄 한국어 메시지
```
JSON으로 반환해도 무방하나, 클라이언트는 본문 텍스트를 그대로 표시하므로 **사용자 친화적인 메시지**여야 한다.

---

## 5. 응답 예시 (4가지 판정 시나리오)

### 5.1 `T` — 일치
```json
{
  "request_id": "req-2026-05-14-abc123",
  "article": {
    "url": "https://news.example.com/article-1",
    "title": "2023년 청년실업률 5.9%...전년比 소폭 개선",
    "published_at": "2024-01-15T09:00:00Z"
  },
  "claim": {
    "claim_id": "claim-001",
    "raw_text": "2023년 청년(15~29세) 실업률은 5.9%였다.",
    "claim_type": "absolute",
    "year": 2023, "compare_year": null,
    "item": "청년 실업률", "value": 5.9, "unit": "%",
    "population": "15~29세", "aggregation": "연간 평균",
    "cited_source": "통계청 고용동향"
  },
  "all_claims": [],
  "verdict": "T",
  "confidence": 0.92,
  "evidence": {
    "table_id": "DT_1DA7001S", "org_id": "101",
    "table_name": "고용동향 - 실업률 (연령별)",
    "table_url": "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1DA7001S",
    "period": "2023",
    "classification": { "C1": "청년층 (15~29세)" },
    "official_value": 5.9, "official_unit": "%",
    "retrieved_at": "2024-01-15T09:05:00Z"
  },
  "comparison": {
    "article_value": 5.9, "official_value": 5.9, "unit": "%",
    "abs_diff": 0, "rel_diff_pct": 0,
    "tolerance_pct": 0.1, "within_tolerance": true
  },
  "explanation": "이 기사는 2023년 청년(15~29세) 실업률을 5.9%로 인용하였습니다. ...",
  "pipeline": [
    { "step": 1, "name": "기사 내용 추출",        "status": "done", "duration_ms": 420 },
    { "step": 2, "name": "주장 탐지",            "status": "done", "duration_ms": 1850 },
    { "step": 3, "name": "주장 분류",            "status": "done", "duration_ms": 980 },
    { "step": 4, "name": "주장 구조화 (8-슬롯)", "status": "done", "duration_ms": 1340 },
    { "step": 5, "name": "KOSIS 카탈로그 필터링","status": "done", "duration_ms": 210 },
    { "step": 6, "name": "임베딩 검색 (Top-50)", "status": "done", "duration_ms": 760 },
    { "step": 7, "name": "재순위화 (Top-5)",     "status": "done", "duration_ms": 890 },
    { "step": 8, "name": "RAG 추론 (Top-1)",     "status": "done", "duration_ms": 2100 },
    { "step": 9, "name": "KOSIS API + 수치 비교","status": "done", "duration_ms": 1450 }
  ]
}
```

### 5.2 `N` — 매칭 통계 없음 (중간 단계에서 중단)
핵심: `evidence: null`, `comparison: null`, pipeline은 중단된 단계 `error` + 이후 단계 모두 `skipped`.
```json
{
  "verdict": "N",
  "confidence": 0,
  "evidence": null,
  "comparison": null,
  "explanation": "이 기사의 주장에 대응하는 KOSIS 통계표를 찾을 수 없었습니다. ...",
  "pipeline": [
    { "step": 1, "name": "기사 내용 추출",        "status": "done",    "duration_ms": 380 },
    { "step": 2, "name": "주장 탐지",            "status": "done",    "duration_ms": 1700 },
    { "step": 3, "name": "주장 분류",            "status": "done",    "duration_ms": 920 },
    { "step": 4, "name": "주장 구조화 (8-슬롯)", "status": "done",    "duration_ms": 1280 },
    { "step": 5, "name": "KOSIS 카탈로그 필터링","status": "done",    "duration_ms": 200 },
    { "step": 6, "name": "임베딩 검색 (Top-50)", "status": "error",   "duration_ms": 890 },
    { "step": 7, "name": "재순위화 (Top-5)",     "status": "skipped", "duration_ms": null },
    { "step": 8, "name": "RAG 추론 (Top-1)",     "status": "skipped", "duration_ms": null },
    { "step": 9, "name": "KOSIS API + 수치 비교","status": "skipped", "duration_ms": null }
  ]
}
```

> 추가 예시(F 불일치, M 모호, 전망치 스킵)는 `web/src/lib/api/mock.ts` 의 `SCENARIOS` 배열 참조.

---

## 6. 백엔드 구현 체크리스트

- [ ] `POST /verify` 라우트 마운트, JSON 요청/응답
- [ ] CORS: 개발 단계에서 `http://localhost:5173` (Vite 기본) 허용
- [ ] 응답 전체가 §2 zod 스키마(`web/src/lib/api/schema.ts`)를 통과
- [ ] §3 변환 규칙을 적용해 Pipeline 모델 → API 응답 생성
- [ ] `verdict` ↔ `evidence`/`comparison` null 일관성:
  - `verdict='T' or 'F'` → `evidence`, `comparison` 모두 non-null
  - `verdict='N'` → 둘 다 `null` 가능
  - `verdict='M'` → 케이스에 따라 `evidence`만 있을 수도, 둘 다 null일 수도 있음
- [ ] `pipeline`은 항상 길이 9, 단계 순서대로
- [ ] `confidence` 는 0~1 실수
- [ ] `tolerance_pct` 는 소수(0.05), `rel_diff_pct`는 퍼센트 숫자(31.9) — 단위 혼동 주의
- [ ] `retrieved_at`은 ISO 8601 datetime (zod `.datetime()` 통과) — **타임존 필수**
- [ ] `published_at`은 `Date.parse()` 가능한 문자열(ISO 8601 권장) — 검증은 통과해도 파싱 실패 시 "Invalid Date" 노출
- [ ] `table_url`은 절대 URL
- [ ] 사용자 메시지가 될 가능성이 있는 에러는 한국어 사용자 친화 문구로
- [ ] 정상 응답은 90초 이내

---

## 7. 변경 절차

이 계약을 변경할 때:
1. 변경이 백엔드 내부 모델에 영향이 있다면 `docs/PIPELINE_SCHEMA.md` 먼저 갱신
2. `web/src/lib/api/schema.ts` 수정 (응답 SSOT)
3. 본 문서(`docs/WEB_API_CONTRACT.md`) 동기화 — §2 응답 스키마와 §3 변환 규칙 양쪽
4. `web/src/lib/api/mock.ts` 시나리오 갱신 (프론트 단독 개발/시연용)
5. 백엔드 구현 갱신 후 통합 테스트
