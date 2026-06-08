# Claim Extractor 테스트 결과

**날짜:** 2026-06-02  
**테스트 파일:** `tests/test_claim_extractor.py`  
**대상 모듈:** `src/modules/extract_statistical_claims.py`, `src/modules/normalize_claim.py`

---

## 무엇을 테스트했나요?

가짜 뉴스 탐지 파이프라인에서 **기사 본문 → 주장 추출 → 수치 정규화** 흐름을 담당하는 두 모듈을 테스트했습니다.

### 모듈 1: `extract_statistical_claims` (주장 추출)

기사 본문을 받아서 **"이 기사에 수치적 사실 주장이 몇 개 있고, 각각 어떤 내용인가"** 를 뽑아내는 모듈입니다.  
예를 들어 _"2024년 합계출산율은 0.72명이다"_ 라는 문장에서 아래 정보를 구조화해서 추출합니다.

- 어떤 문장인지 (`sentence`)
- 무엇에 대한 수치인지 (`subject`: 합계출산율)
- 수치가 얼마인지 (`value.raw`: 0.72명)
- 어느 시점 데이터인지 (`period_value.raw`: 2024년)
- 단위는 무엇인지 (`unit`: 명)
- 출처는 어디인지 (`cited_source`: 통계청)

### 모듈 2: `normalize_claim` (수치 정규화)

추출된 주장의 수치와 시점을 **컴퓨터가 비교하기 좋은 형태로 다듬는** 모듈입니다.  
예를 들어 `"0.72명"` → `"0.72"`, `"2024년"` → `"2024"` 처럼 단위·조사를 제거해 순수한 숫자값만 남깁니다.  
이 값은 나중에 KOSIS 공식 통계 수치와 직접 비교할 때 쓰입니다.

---

## 어떻게 확인했나요?

아래 5가지 항목을 체크했습니다.

| # | 테스트명 | 확인 방법 |
|---|----------|-----------|
| 1 | `test_extract_populates_claims` | 모듈 실행 후 `claims` 리스트가 비어 있지 않은지 확인 |
| 2 | `test_extract_claim_fields` | 추출된 claim의 필수 필드(`claim_id`, `article_id`, `sentence` 등)가 모두 채워졌는지 확인 |
| 3 | `test_extract_value_slot_raw_not_empty` | `value.raw`(수치 원문), `period_value.raw`(시점 원문)가 비어 있지 않은지 확인 |
| 4 | `test_normalize_fills_llm_value` | normalize 실행 후 `value.llm_value`, `period_value.llm_value`가 채워졌는지 확인 |
| 5 | `test_normalize_no_claims_is_noop` | 주장이 없는 빈 record에서 normalize를 호출해도 오류 없이 넘어가는지 확인 |

**결과: 5개 모두 통과 (5 passed, 0.12s)**

---

## 결과값이 무엇을 의미하나요?

실제로 두 모듈을 순서대로 실행했을 때 데이터가 어떻게 바뀌는지 단계별로 보여드립니다.

---

### Step 1 — 시작 상태 (아무것도 추출되기 전)

```
claims: []
```

파이프라인이 시작되면 `claims`는 빈 리스트입니다. 아직 기사를 분석하지 않은 상태입니다.

---

### Step 2 — `extract_statistical_claims` 실행 후

```json
{
  "claim_id": "clm-0001",
  "article_id": "art-0042",
  "sentence": "(더미) 2024년 합계출산율은 0.72명이다.",
  "claim_type": "수치",
  "subject": "합계출산율",
  "value": {
    "raw": "0.72명",
    "llm_value": "",
    "is_inferred": false
  },
  "unit": "명",
  "aggregation": "값",
  "period_type": "Y",
  "period_value": {
    "raw": "2024년",
    "llm_value": "",
    "is_inferred": false
  },
  "compare_period_value": null,
  "population": "전국",
  "cited_source": "통계청"
}
```

기사 본문에서 주장 1건이 추출됐습니다. 각 필드의 의미는 다음과 같습니다.

| 필드 | 값 | 의미 |
|------|-----|------|
| `claim_id` | `"clm-0001"` | 이 주장의 고유 식별자 |
| `article_id` | `"art-0042"` | 어느 기사에서 나온 주장인지 |
| `sentence` | `"(더미) 2024년 합계출산율은 0.72명이다."` | 원문 문장 |
| `subject` | `"합계출산율"` | 무엇에 대한 수치인지 |
| `value.raw` | `"0.72명"` | 기사에 적힌 수치 그대로 |
| `value.llm_value` | `""` | 아직 정규화 전이라 비어 있음 |
| `period_type` | `"Y"` | 연간(Year) 데이터 |
| `period_value.raw` | `"2024년"` | 기사에 적힌 시점 그대로 |
| `period_value.llm_value` | `""` | 아직 정규화 전이라 비어 있음 |
| `population` | `"전국"` | 어느 범위의 통계인지 |
| `cited_source` | `"통계청"` | 기사가 인용한 출처 |

> `value.llm_value`와 `period_value.llm_value`가 비어 있는 것이 정상입니다.  
> 이 값은 다음 단계인 normalize에서 채워집니다.

---

### Step 3 — `normalize_claim` 실행 후

```json
{
  "claim_id": "clm-0001",
  "article_id": "art-0042",
  "sentence": "(더미) 2024년 합계출산율은 0.72명이다.",
  "claim_type": "수치",
  "subject": "합계출산율",
  "value": {
    "raw": "0.72명",
    "llm_value": "0.72",
    "is_inferred": false
  },
  "unit": "명",
  "aggregation": "값",
  "period_type": "Y",
  "period_value": {
    "raw": "2024년",
    "llm_value": "2024",
    "is_inferred": false
  },
  "compare_period_value": null,
  "population": "전국",
  "cited_source": "통계청"
}
```

`llm_value` 두 곳이 채워졌습니다.

| 필드 | 변환 전 | 변환 후 | 의미 |
|------|---------|---------|------|
| `value.llm_value` | `""` | `"0.72"` | `"0.72명"` 에서 단위 제거 → 순수 수치 |
| `period_value.llm_value` | `""` | `"2024"` | `"2024년"` 에서 조사 제거 → 순수 연도 |

이 값들이 이후 KOSIS 공식 통계 수치와 직접 비교되어 **해당 주장이 사실인지 아닌지** 를 판별하는 데 사용됩니다.

---

## 현재 상태 및 다음 단계

두 모듈은 현재 **더미(happy-path) 구현** 상태입니다. 실제 LLM(HCX)이 연결되면 아래 테스트를 추가로 작성할 필요가 있습니다.

- 실제 기사 본문에서 주장이 올바르게 추출되는지 검증
- `"약 23만 명"` → `"230000"`, `"전년"` → `"2023"` 같은 복잡한 한국어 수치·시점 정규화 검증
- LLM 응답 파싱이 실패했을 때 `ExtractStatisticalClaimsError` / `NormalizeClaimError` 가 제대로 발생하는지 검증
