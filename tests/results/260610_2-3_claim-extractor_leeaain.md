# Claim Extractor 테스트 결과 (재테스트)

**날짜:** 2026-06-10
**테스트 파일:** 직접 실행 (`extract_statistical_claims` → `normalize_claim` 라이브)
**대상 모듈:** `src/modules/extract_statistical_claims.py`, `src/modules/normalize_claim.py`
**이전 결과:** `tests/results/test_claim_extractor_result.md` (2026-06-02, 더미 구현 기준)

---

## 왜 다시 테스트했나요?

2026-06-02 이전 결과는 **더미(happy-path) 구현** 기준이었습니다. 이후 extractor·normalize 가 크게 바뀌어 재검증이 필요했습니다.

| 변경 | 시점 | 내용 |
|---|---|---|
| claim_type 분류 구현 | 2026-06-08 | `"수치"` 더미 → **7종 enum**(absolute/change_rate/ratio/distribution/comparison/metaphoric/verifiable) |
| ComparisonSpec 도입 | 2026-06-08 | 원자 분리 비교용 `compare_conquer` 필드 추가 |
| 실제 LLM(HCX) 연결 | — | `"(더미)..."` 고정 출력 → **기사 본문에서 실제 추출** |
| `%` 정규화 수정 | 2026-06-10 | `5.9%` → `0.059`(÷100) 버그 제거 → **`5.9`(% 스케일 보존)** |

---

## 무엇을 테스트했나요?

기사 본문 → **주장 추출([2]) → 수치 정규화([3])** 흐름을 실제 LLM 로 검증했습니다.

### 모듈 1: `extract_statistical_claims` (주장 추출)
기사 본문에서 수치적 사실 주장을 뽑아 구조화합니다. 이전과 달리 **claim_type(주장 유형)을 7종으로 분류**하고, **population(대상 집단)·compare_conquer(비교 그룹)** 까지 채웁니다.

### 모듈 2: `normalize_claim` (수치 정규화)
`"0.72명"` → `"0.72"`, `"5.9%"` → `"5.9"`, `"2024년"` → `"2024"` 처럼 단위·조사를 떼어 비교용 값을 만듭니다. (`%` 는 KOSIS 와 같은 % 스케일로 보존)

---

## 입력 기사

> 통계청에 따르면 2024년 합계출산율은 0.72명으로 집계됐다. 2023년 청년 실업률은 5.9%였다.

두 문장 → **주장 2건** 추출됨.

---

## 결과값이 무엇을 의미하나요?

### Step 1 — 시작 상태
```
claims: []
```

### Step 2 — `extract_statistical_claims` 실행 후 (LLM)
```json
[
  {
    "claim_id": "clm-0001",
    "sentence": "통계청에 따르면 2024년 합계출산율은 0.72명으로 집계됐다.",
    "claim_type": "absolute",
    "subject": "합계출산율",
    "value": { "raw": "0.72명", "llm_value": "", "is_inferred": false },
    "unit": "명",
    "period_type": "Y",
    "period_value": { "raw": "2024년", "llm_value": "", "is_inferred": false },
    "compare_conquer": null,
    "population": "불명",
    "cited_source": "통계청"
  },
  {
    "claim_id": "clm-0002",
    "sentence": "2023년 청년 실업률은 5.9%였다.",
    "claim_type": "absolute",
    "subject": "청년 실업률",
    "value": { "raw": "5.9%", "llm_value": "", "is_inferred": false },
    "unit": "%",
    "period_type": "Y",
    "period_value": { "raw": "2023년", "llm_value": "", "is_inferred": false },
    "compare_conquer": null,
    "population": "청년",
    "cited_source": "통계청"
  }
]
```

이전 결과와 달라진 점:
- `claim_type`: `"수치"`(더미) → **`"absolute"`**(7종 분류 작동)
- `population`: 문장에서 실제 추출 (`"청년"`) — 없으면 `"불명"`
- `value.llm_value`/`period_value.llm_value` 는 정규화 전이라 비어 있음(정상)

### Step 3 — `normalize_claim` 실행 후
```json
[
  {
    "claim_id": "clm-0001", "subject": "합계출산율",
    "value": { "raw": "0.72명", "llm_value": "0.72" },
    "period_value": { "raw": "2024년", "llm_value": "2024" }
  },
  {
    "claim_id": "clm-0002", "subject": "청년 실업률",
    "value": { "raw": "5.9%", "llm_value": "5.9" },
    "period_value": { "raw": "2023년", "llm_value": "2023" }
  }
]
```

| 필드 | 변환 전 | 변환 후 | 의미 |
|---|---|---|---|
| `value.llm_value` (출산율) | `""` | `"0.72"` | `"0.72명"` 단위 제거 |
| `value.llm_value` (실업률) | `""` | **`"5.9"`** | `"5.9%"` → **÷100 안 함**(% 스케일 보존, 버그 수정) |
| `period_value.llm_value` | `""` | `"2024"` / `"2023"` | `"...년"` 조사 제거 |

> 이전 버그였다면 `"5.9%"` → `"0.059"` 로 변환돼 KOSIS(5.9 % 스케일)와 100배 어긋났을 것. 지금은 `5.9` 로 정확히 보존된다.

---

## 결론

| 항목 | 이전(2026-06-02 더미) | 현재(2026-06-10 라이브) |
|---|---|---|
| 추출 | 더미 고정 1건 | **기사에서 실제 N건** |
| claim_type | `"수치"` | **7종 분류(absolute 등)** |
| population | `"전국"` 고정 | **문장에서 추출** |
| `%` 정규화 | (해당 없음) | **% 스케일 보존(5.9→5.9)** |

→ extractor·normalize 가 더미에서 **실제 LLM 기반 + claim_type 분류 + % 스케일 정합**으로 발전했고, 재테스트에서 모두 정상 동작 확인.

작성: leeaain, 2026-06-10
