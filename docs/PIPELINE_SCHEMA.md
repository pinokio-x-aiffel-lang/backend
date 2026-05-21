# Pipeline Schema

> **대상 독자**: 백엔드 개발자. 파이프라인 런타임·저장 모델 명세.
> (프론트엔드는 본 문서를 볼 필요 없음 — 외부 API 응답 형식은 `docs/WEB_API_CONTRACT.md` 참조)

런타임 중에는 아래 세 스키마(Article / Claim / Analysis)를 하나의 상위 객체로 묶어 9단계 파이프라인 끝까지 순회한다. 파이프라인 종료 시 세 스키마를 분리하여 각각의 DB 테이블(`articles` / `claims` / `analyses`)에 저장한다.

---

## 공통 규칙

### 식별자
| 식별자 | 형식 | 예시 |
|--------|------|------|
| `article_id` | `{source}_{YYYYMMDD}_{hash4}` | `chosun_20250314_a3f2` |
| `claim_id` | `{article_id}_c{NN}` | `chosun_20250314_a3f2_c01` |
| `evidence_id` | `ev_{claim_id}_{NN}` | `ev_chosun_20250314_a3f2_c01_01` |

`hash4`: 본문 또는 URL의 SHA-256 앞 4자리 16진수.

### 날짜·시각
- 날짜만: ISO 8601 `YYYY-MM-DD` (예: `2025-03-14`)
- 타임스탬프: ISO 8601 + **타임존 필수** (예: `2026-05-11T09:12:03Z`, `2026-05-11T18:12:03+09:00`)

### 누락값
모르면 `null`. 빈 문자열 `""` 사용 금지.

### `Originalvalue` 객체
Claim의 `value`, `period_value`, `compare_period_value`에 공통 적용되는 3-필드 객체.

| 필드 | 타입 | 설명 |
|------|------|------|
| `Original_table` | string | 본문 표기 그대로 (예: `"약 23만"`, `"전년"`) |
| `LLM_Metrics` | string | LLM이 정규화한 표준 표현 (예: `"230000"`, `"2023"`) |
| `Inferred` | bool | 본문에 명시 안 됨/문맥 추론이면 `true` |

비교·검증 로직은 항상 `LLM_Metrics`를 사용.

---

## 1. Article 스키마

| 필드 | 타입 | nullable | 설명 |
|------|------|:---:|------|
| `article_id` | string | ❌ | |
| `title` | string | ❌ | 기사 제목 |
| `content` | string | ❌ | 본문 전체 텍스트 (HTML 태그 제거 후) |
| `published_at` | string (date) | ❌ | |
| `source` | string (enum) | ❌ | 언론사 단축 코드 (예: `chosun`) |

```json
{
  "article_id": "chosun_20250314_a3f2",
  "title": "지난해 합계출산율 0.72명, 역대 최저 수준",
  "content": "통계청에 따르면 2024년 합계출산율은 0.72명으로 전년(2023년)과 같은 수준을 유지했다. 출생아 수는 약 23만명으로 집계됐다. ...(이하 본문 전체)...",
  "published_at": "2025-03-14",
  "source": "chosun"
}
```

---

## 2. Claim 스키마

기사 1건당 N개 주장이 추출되며, 모두 `claims[]`로 묶임.

| 필드 | 타입 | nullable | 설명 |
|------|------|:---:|------|
| `claim_id` | string | ❌ | |
| `article_id` | string | ❌ | FK → Article.article_id |
| `sentence` | string | ❌ | 주장이 추출된 원문 문장 |
| `claim_type` | enum (string) | ❌ | 예: `규모` |
| `subject` | string | ❌ | 주장 주제 (예: "합계출산율") |
| `value` | Originalvalue | ❌ | 주장 수치 |
| `unit` | string | ❌ | 단위 (예: "명", "%") |
| `aggregation` | enum (string) | ❌ | 예: `합계`, `비율` |
| `period_type` | enum (string) | ❌ | 예: `Y` (연) |
| `period_value` | Originalvalue | ❌ | 시점 |
| `compare_period_value` | Originalvalue | ✅ | 비교 시점 |
| `population` | string | ❌ | 모집단 (예: "전국") |
| `cited_source` | string | ❌ | 기사 내 인용 표기 (예: "통계청") |

```json
{
  "claims": [
    {
      "claim_id": "chosun_20250314_a3f2_c01",
      "article_id": "chosun_20250314_a3f2",
      "sentence": "통계청에 따르면 2024년 합계출산율은 0.72명으로 전년과 같은 수준을 유지했다.",
      "claim_type": "규모",
      "subject": "합계출산율",
      "value":               { "Original_table": "0.72", "LLM_Metrics": "0.72", "Inferred": false },
      "unit": "명",
      "aggregation": "비율",
      "period_type": "Y",
      "period_value":        { "Original_table": "2024", "LLM_Metrics": "2024", "Inferred": false },
      "compare_period_value":{ "Original_table": "전년", "LLM_Metrics": "2023", "Inferred": true  },
      "population": "전국",
      "cited_source": "통계청"
    },
    {
      "claim_id": "chosun_20250314_a3f2_c02",
      "article_id": "chosun_20250314_a3f2",
      "sentence": "출생아 수는 약 23만명으로 집계됐다.",
      "claim_type": "규모",
      "subject": "출생아 수",
      "value":               { "Original_table": "약 23만", "LLM_Metrics": "230000", "Inferred": true },
      "unit": "명",
      "aggregation": "합계",
      "period_type": "Y",
      "period_value":        { "Original_table": "(앞 문장에서 추론)", "LLM_Metrics": "2024", "Inferred": true },
      "compare_period_value": null,
      "population": "전국",
      "cited_source": "통계청"
    }
  ]
}
```

---

## 3. Analysis 스키마

Claim 1개당 분석 1세트. 상위는 `analysis[]` 배열.

```
analysis[]:
  claim_id     : string        FK → Claim.claim_id
  kosis_search : object        §3.1
  kosis_query  : object        §3.2
  evidence     : object[]      §3.3
  verification : object        §3.4
```

### 3.1 `kosis_search`
| 필드 | 타입 | nullable | 설명 |
|------|------|:---:|------|
| `api` | string | ❌ | 엔드포인트명 (예: `"statisticsSearch.do"`) |
| `query` | string | ❌ | 검색어 |
| `params` | string | ❌ | 호출 파라미터 (JSON 직렬화 문자열) |
| `hits` | int | ❌ | 검색 결과 건수 |
| `selected_tbl_id` | string | ✅ | 선택된 표 ID |
| `selected_tbl_name` | string | ✅ | 선택된 표명 |
| `success` | bool | ❌ | |
| `error_msg` | string | ✅ | 실패 시 메시지 |
| `duration_ms` | int | ❌ | 소요 시간 (밀리초) |

### 3.2 `kosis_query`
| 필드 | 타입 | nullable | 설명 |
|------|------|:---:|------|
| `api` | string | ❌ | (예: `"statisticsData.do"`) |
| `tbl_id` | string | ❌ | 조회한 표 ID |
| `params` | string | ❌ | JSON 직렬화 문자열 |
| `rows_returned` | int | ❌ | 반환 행 수 |
| `success` | bool | ❌ | |
| `error_msg` | string | ✅ | |
| `duration_ms` | int | ❌ | |

### 3.3 `evidence[]` — 수집된 증거 (claim당 0~N개)
| 필드 | 타입 | nullable | 설명 |
|------|------|:---:|------|
| `evidence_id` | string | ❌ | |
| `claim_id` | string | ❌ | FK |
| `source` | string | ❌ | 데이터 출처 (예: `"KOSIS"`) |
| `subject` | string | ❌ | 통계 주제 |
| `value` | float | ❌ | KOSIS 공식 수치 |
| `unit` | string | ❌ | |
| `period_type` | enum (string) | ❌ | 예: `Y` |
| `period_value` | string | ❌ | 시점 (Claim과 달리 단순 문자열) |
| `population` | string | ❌ | |
| `kosis_org_id` | string | ❌ | KOSIS 기관 ID |
| `kosis_tbl_id` | string | ❌ | KOSIS 표 ID |
| `kosis_tbl_name` | string | ❌ | KOSIS 표명 |
| `kosis_item_id` | string | ❌ | KOSIS 항목 ID |
| `kosis_url` | string (URL) | ❌ | KOSIS 통계표 페이지 절대 URL |
| `classification` | `Record<string,string>` | ❌ | 분류 코드→값 |
| `last_updated` | string (date) | ❌ | KOSIS 측 마지막 갱신일 |
| `retrieved_at` | string (datetime) | ❌ | 조회 시각 (타임존 필수) |

### 3.4 `verification`
| 필드 | 타입 | nullable | 설명 |
|------|------|:---:|------|
| `verdict` | enum (string) | ❌ | `일치` / `불일치` / `판단불가` / `모호` |
| `mismatch_type` | enum (string) | ✅ | `verdict='불일치'`일 때만. 그 외 null |
| `claim_value` | string | ❌ | 비교에 사용된 주장 수치 |
| `kosis_value` | string | ❌ | 비교에 사용된 KOSIS 수치 |
| `explanation` | string | ❌ | 자연어 설명 (한국어, 단일 문단) |
| `confidence` | float | ❌ | `[0.0, 1.0]` |
| `llm_model` | string | ❌ | 사용된 모델명 (예: `"HCX-003"`) |

### 3.5 예시
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
        "success": true,
        "error_msg": null,
        "duration_ms": 245
      },

      "kosis_query": {
        "api": "statisticsData.do",
        "tbl_id": "DT_1B8000F",
        "params": "{\"orgId\":\"101\",\"tblId\":\"DT_1B8000F\",\"itmId\":\"T20\",\"objL1\":\"00\",\"prdSe\":\"Y\",\"startPrdDe\":\"2023\",\"endPrdDe\":\"2024\",\"format\":\"json\"}",
        "rows_returned": 2,
        "success": true,
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
          "retrieved_at": "2026-05-11T09:12:03Z"
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
          "retrieved_at": "2026-05-11T09:12:03Z"
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
