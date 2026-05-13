# 슬롯 스키마

AI 뉴스 사실검증 PoC의 데이터 스키마. 파이프라인 3단계 구조에 맞춰 정의됨.

```
기사 원문  →  소형 슬롯 (주장 추출)  →  대형 슬롯 (검증 분석)
```

> 키 네이밍 규칙: 모든 키는 영문 사용. 예시 값(주장 내용, 출처, 단위 등)은 한글 그대로 유지 — 실제 데이터가 한국어이기 때문.

---

## 1. 기사 원문 스키마

뉴스 원문을 그대로 담는 입력 스키마.

```json
{
  "article_id": "chosun_20250314_a3f2",
  "title": "지난해 합계출산율 0.72명, 역대 최저 수준",
  "content": "통계청에 따르면 2024년 합계출산율은 0.72명으로 전년(2023년)과 같은 수준을 유지했다. 출생아 수는 약 23만명으로 집계됐다. ...(이하 본문 전체)...",
  "published_at": "2025-03-14",
  "source": "chosun"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `article_id` | string | 기사 고유 ID. `{매체}_{발행일}_{해시}` 형식 |
| `title` | string | 기사 제목 |
| `content` | string | 기사 본문 전체 |
| `published_at` | string (YYYY-MM-DD) | 발행일 |
| `source` | string | 매체 코드 (예: `chosun`, `donga`) |

---

## 2. 소형 슬롯 스키마 (Claims)

기사에서 추출한 **수치 기반 사실 주장**만 담긴다. 한 기사에서 여러 claim이 나올 수 있어 배열.

아래 예시는 한 기사에서 두 개의 claim이 추출된 경우.
- `c01`: 명시적 수치 + 비교 시점(`전년`) 자연어 표현
- `c02`: 근사 표현(`약`) + 시점이 앞 문장에서 추론된 자연어 케이스

```json
{
  "claims": [
    {
      "claim_id": "chosun_20250314_a3f2_c01",
      "article_id": "chosun_20250314_a3f2",
      "sentence": "통계청에 따르면 2024년 합계출산율은 0.72명으로 전년과 같은 수준을 유지했다.",
      "claim_type": "규모",
      "subject": "합계출산율",
      "value": {
        "Original_table": "0.72",
        "LLM_Metrics": "0.72",
        "Inferred": false
      },
      "unit": "명",
      "aggregation": "비율",
      "period_type": "Y",
      "period_value": {
        "Original_table": "2024",
        "LLM_Metrics": "2024",
        "Inferred": false
      },
      "compare_period_value": {
        "Original_table": "전년",
        "LLM_Metrics": "2023",
        "Inferred": true
      },
      "population": "전국",
      "cited_source": "통계청"
    },
    {
      "claim_id": "chosun_20250314_a3f2_c02",
      "article_id": "chosun_20250314_a3f2",
      "sentence": "출생아 수는 약 23만명으로 집계됐다.",
      "claim_type": "규모",
      "subject": "출생아 수",
      "value": {
        "Original_table": "약 23만",
        "LLM_Metrics": "230000",
        "Inferred": true
      },
      "unit": "명",
      "aggregation": "합계",
      "period_type": "Y",
      "period_value": {
        "Original_table": "(앞 문장에서 추론)",
        "LLM_Metrics": "2024",
        "Inferred": true
      },
      "compare_period_value": null,
      "population": "전국",
      "cited_source": "통계청"
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `claim_id` | string | 주장 고유 ID. `{article_id}_c{번호}` 형식 |
| `article_id` | string | 소속 기사 ID (FK) |
| `sentence` | string | 주장이 추출된 원문 문장 |
| `claim_type` | string | 주장 유형 (예: `규모`, `비교`, `추세`, `구성`, `인과`) |
| `subject` | string | 주장의 대상 지표 (예: `합계출산율`) |
| `value` | object | 주장의 핵심 수치 (아래 구조) |
| `value.Original_table` | string | 기사 원문 그대로의 표현 |
| `value.LLM_Metrics` | string | LLM이 정규화한 수치 |
| `value.Inferred` | boolean | LLM 정규화·추론이 필요했는지 (`전년`, `약 23만`, 문맥 추론 등 → `true`) |
| `unit` | string | 단위 (예: `명`, `%`, `원`, `건`) |
| `aggregation` | string | 집계 방식 (예: `비율`, `합계`, `평균`, `중앙값`) |
| `period_type` | string | 기간 유형. `Y`=년, `M`=월, `Q`=분기, `D`=일 |
| `period_value` | object | 기준 시점 (구조는 `value`와 동일) |
| `compare_period_value` | object \| null | 비교 시점. 비교 주장이 아닐 시 `null` |
| `population` | string | 모집단 (예: `전국`, `서울`, `15~64세`) |
| `cited_source` | string | 기사가 인용한 출처 (예: `통계청`, `한국은행`) |

---

## 3. 대형 슬롯 스키마 (Analysis)

KOSIS API 호출 로그, 외부 근거, LLM 검증 결과까지 모두 담는 분석 스키마.
`claim_id`로 소형 슬롯과 1:1 매칭.

```json
{
  "analysis": [
    {
      "claim_id": "chosun_20250314_a3f2_c01",

      "kosis_search": {
        "api": "statisticsSearch.do",
        "query": "합계출산율",
        "params": "{\"searchNm\":\"합계출산율\",\"format\":\"json\"}",
        "hits": 7,
        "selected_tbl_id": "DT_1B8000F",
        "selected_tbl_name": "출생아수, 합계출산율, 자연증가 등",
        "success": 1,
        "error_msg": null,
        "duration_ms": 245
      },

      "kosis_query": {
        "api": "statisticsData.do",
        "tbl_id": "DT_1B8000F",
        "params": "{\"orgId\":\"101\",\"tblId\":\"DT_1B8000F\",\"itmId\":\"T20\",\"objL1\":\"00\",\"prdSe\":\"Y\",\"startPrdDe\":\"2023\",\"endPrdDe\":\"2024\",\"format\":\"json\"}",
        "rows_returned": 2,
        "success": 1,
        "error_msg": null,
        "duration_ms": 312
      },

      "evidence": [
        {
          "evidence_id": "ev_chosun_20250314_a3f2_c01_01",
          "claim_id": "chosun_20250314_a3f2_c01",
          "source": "KOSIS",
          "subject": "합계출산율",
          "value": 0.72,
          "unit": "명",
          "period_type": "Y",
          "period_value": "2024",
          "population": "전국",
          "kosis_org_id": "101",
          "kosis_tbl_id": "DT_1B8000F",
          "kosis_tbl_name": "출생아수, 합계출산율, 자연증가 등",
          "kosis_item_id": "T20",
          "kosis_url": "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1B8000F",
          "classification": { "C1": "00(행정구역별-전국)" },
          "last_updated": "2025-02-26",
          "retrieved_at": "2026-05-11T09:12:03"
        },
        {
          "evidence_id": "ev_chosun_20250314_a3f2_c01_02",
          "claim_id": "chosun_20250314_a3f2_c01",
          "source": "KOSIS",
          "subject": "합계출산율",
          "value": 0.72,
          "unit": "명",
          "period_type": "Y",
          "period_value": "2023",
          "population": "전국",
          "kosis_org_id": "101",
          "kosis_tbl_id": "DT_1B8000F",
          "kosis_tbl_name": "출생아수, 합계출산율, 자연증가 등",
          "kosis_item_id": "T20",
          "kosis_url": "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1B8000F",
          "classification": { "C1": "00(행정구역별-전국)" },
          "last_updated": "2025-02-26",
          "retrieved_at": "2026-05-11T09:12:03"
        }
      ],

      "verification": {
        "verdict": "일치",
        "mismatch_type": null,
        "claim_value": "0.72",
        "kosis_value": "0.72",
        "explanation": "기사의 2024년 합계출산율 0.72명은 통계청 인구동향조사 공식 수치(0.72명)와 정확히 일치합니다. '전년과 같은 수준'이라는 표현도 2023년 0.72명과 동일하여 사실에 부합합니다.",
        "confidence": 0.97,
        "llm_model": "HCX-003"
      }
    }
  ]
}
```

### 3.1 `kosis_search` — KOSIS 통계표 검색 결과

| 필드 | 타입 | 설명 |
|---|---|---|
| `api` | string | 호출한 KOSIS API 이름 |
| `query` | string | 검색어 |
| `params` | string (JSON) | 호출 파라미터 원문 |
| `hits` | int | 검색 결과 개수 |
| `selected_tbl_id` | string | LLM이 선택한 통계표 ID |
| `selected_tbl_name` | string | 선택한 통계표 이름 |
| `success` | int (0/1) | 성공 여부 |
| `error_msg` | string \| null | 에러 메시지 |
| `duration_ms` | int | 호출 소요 시간 (ms) |

### 3.2 `kosis_query` — KOSIS 통계 데이터 조회 결과

| 필드 | 타입 | 설명 |
|---|---|---|
| `api` | string | 호출한 KOSIS API 이름 |
| `tbl_id` | string | 조회한 통계표 ID |
| `params` | string (JSON) | 호출 파라미터 (시점, 항목 등) 원문 |
| `rows_returned` | int | 반환된 데이터 행 수 |
| `success` | int (0/1) | 성공 여부 |
| `error_msg` | string \| null | 에러 메시지 |
| `duration_ms` | int | 호출 소요 시간 (ms) |

### 3.3 `evidence[]` — 외부 근거 데이터 (배열)

claim의 기준 시점과 비교 시점이 다르면 2개 이상의 evidence가 생긴다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `evidence_id` | string | 근거 고유 ID |
| `claim_id` | string | 소속 claim ID (FK) |
| `source` | string | 출처 (예: `KOSIS`) |
| `subject` | string | 대상 지표 |
| `value` | number | 공식 수치 |
| `unit` | string | 단위 |
| `period_type` | string | 기간 유형 (`Y`/`M`/`Q`/`D`) |
| `period_value` | string | 시점 값 |
| `population` | string | 모집단 |
| `kosis_org_id` | string | KOSIS 기관 ID |
| `kosis_tbl_id` | string | KOSIS 통계표 ID |
| `kosis_tbl_name` | string | KOSIS 통계표 이름 |
| `kosis_item_id` | string | KOSIS 항목 ID |
| `kosis_url` | string | KOSIS 원본 URL |
| `classification` | object | 분류 코드 (지역, 성별 등) |
| `last_updated` | string (YYYY-MM-DD) | 통계 최종 갱신일 |
| `retrieved_at` | string (ISO 8601) | 데이터 조회 시각 |

### 3.4 `verification` — LLM 검증 결과

| 필드 | 타입 | 설명 |
|---|---|---|
| `verdict` | string | 판정 (`일치`, `불일치`, `부분일치`, `검증불가`) |
| `mismatch_type` | string \| null | 불일치 유형 (수치오류, 시점오류, 단위오류, 모집단오류 등) |
| `claim_value` | string | 기사 주장 수치 |
| `kosis_value` | string | KOSIS 공식 수치 |
| `explanation` | string | LLM의 판정 근거 설명 |
| `confidence` | number (0~1) | LLM 신뢰도 |
| `llm_model` | string | 사용한 LLM 모델 (예: `HCX-003`) |

---

## 사용법 (팀원용)

클로드에 이 문서를 첨부한 뒤 다음과 같이 요청:

> "이게 우리 슬롯 스키마야. 첨부한 [기사/주장/분석] 데이터를 이 스키마에 맞춰서 [추출/변환/검증]해줘."

- **기사 → 소형 슬롯**: 기사 원문을 주고 `claims[]` 배열로 추출 요청
- **소형 → 대형 슬롯**: claim과 KOSIS 응답을 주고 `analysis[]` 항목 생성 요청
- **검증**: 대형 슬롯의 `evidence`와 claim을 비교해 `verification` 채우기 요청
