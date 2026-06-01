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

---

## 구현 아키텍처 (코드 구조)

> §1~3은 *데이터 형태* 명세, 이 절은 *코드 구조·설계 결정* 명세다.
> (정립일: 2026-05-31, **흐름 방식 결정: 2026-06-01 — option 2 채택**)

### A. 핵심 원칙
- **데이터(스키마)와 동작(로직)을 분리**한다: 스키마는 `src/schemas/`, 단계 동작은 `src/modules/`(또는 runner 인라인).
- **`MasterSchema`(런타임 스키마)가 직접 파이프라인을 흐른다.** 별도 ctx를 두지 않는다.
- 각 단계는 **`record`(MasterSchema)를 받아 자기 필드만 제자리에서 채운다** (`(record: MasterSchema) -> None`).
- 실패는 **`raise`** — runner가 받아 `StepEvent(error)`로 변환·중단한다 (성공/실패 봉투 없음).
- **DTO는 시스템 경계(HTTP)에만** 둔다.

### B. 폴더 구조
```
src/
  schemas/
    __init__.py        # 공개 façade — runtime.py 의 모델을 re-export
    runtime.py         # 런타임/도메인 스키마 전체 (1파일로 통합)
  modules/             # 파이프라인 단계 구현 (단계당 1파일)
    load_article.py, extract_statistical_claims.py, ...
  pipeline/
    runner.py          # 단계 조립·실행, MasterSchema 생성·흐름, 이벤트 스트리밍
    events.py          # StepEvent / ResultEvent(record: MasterSchema)
  api/
    verify.py          # /verify 의 HTTP 요청/응답 DTO (VerifyRequest 등)
    schemas.py, main.py, routers/, providers/   # 별도 앱(LLM 게이트웨이)
  services/verify_service.py   # 파이프라인 ↔ HTTP 연결
docs/slot_schema_master.json   # 사람용 예시 1건 (코드가 로드 안 함)
main.py                        # 검증 제품 FastAPI 앱 (/verify, /verify/stream)
```

### C. 런타임 스키마 (`src/schemas/runtime.py`)
- 단일 파일에 도메인 모델 13개 + 루트 **`MasterSchema`**(옛 `SlotSchemaMaster`).
- 파이프라인을 직접 흐르므로 **상위 필드는 Optional**(`article`/`verifications` = `... | None = None`, 진행 중 미완성 허용).
- `content`(원본 입력 URL/본문)는 **`exclude=True` 투명 필드** — 흐르되 `model_dump()` 직렬화에는 빠진다.
- Pydantic = 데이터 형태 + 런타임 검증, 비즈니스 로직 없음. 필드 명세는 §1~3. `__init__.py` façade 경유 사용.
- 스키마 개념별 분해는 검토했으나 **통합(1파일) 선택** — 모델이 작고 밀결합이라 단순함 우선.

### D. MasterSchema 직접 흐름 (option 2)
- 검토한 3안: ① 단계별 입출력 DTO  ② **대형 스키마 직접 흐름(채택)**  ③ ctx + 끝단 병합.
- 채택 이유: 타입 하나로 단순 — 누산기와 도메인 레코드를 분리하지 않는다.
- 대가: 흐르려면 미완성 상태가 합법이어야 해 **상위 필드를 Optional로 풀었다** → 도메인 타입이 "완성 보장"을 잃는다. 소비자(DB/API)는 필요 시 None 체크.
- (선택) 각 단계의 read/write 표면을 **Protocol**로 좁힐 수 있으나, 현재는 단순화를 위해 `record: MasterSchema`를 그대로 받는다. 좁히려면 전 단계 일괄 적용.

### E. 단계(step) 규칙
- 시그니처: **`async def step(record: MasterSchema) -> None`** — 받은 record를 제자리에서 채움, 반환 없음.
- runner 루프: `await fn(record)` (반환 재할당 없음).
- 실패: **`raise`** (예: `ArticleLoadError`). runner `try/except`가 `StepEvent(error)`로 변환·중단.
- 단계 구현은 `src/modules/`로 점진 이전. `load_article.py`가 템플릿. (현재 runner는 인라인 stub 사용.)

### F. 결과 직렬화
- 파이프라인 끝에서 `ResultEvent.record`(MasterSchema)를 그대로 `model_dump()` → SSE `result` 이벤트. `content`는 exclude라 제외.
- **별도 병합/완성 게이트 없음** (전부 Optional). 완성 보장이 필요하면 경계에서 명시 가드(`if record.article is None: ...`)를 둔다.

### G. 네이밍 / 결정 이력
- `schemas/claim.py` → `schemas/runtime.py` (파일명)
- 루트 클래스 `SlotSchemaMaster` → `MasterSchema` (클래스명)
- `schemas/slot_schema_master_v2.json` → `docs/slot_schema_master.json` (사람용 참고)
- `schemas/verify.py` → `api/verify.py` (HTTP 경계 DTO)
- 스키마 개념별 분해(article/claim/...) → `runtime.py` 한 파일로 통합
- **흐름 방식: ctx 별도(option 3) 검토 후 → MasterSchema 직접 흐름(option 2) 채택, `PipelineContext` 제거**

### H. 미결정 / 할 일
- **단계 구현 이전**: runner 인라인 stub(`_article_parse` 등)을 `src/modules/*.py`로 옮기고 `_STEPS` 정합 + 실제 로직 채우기.
- **`Article` 메타**: `title`/`source`/`published_at` 필수인데 본문만 입력될 때 (a) Optional 완화 / (b) 플레이스홀더 / (c) 입력 계약에서 받기 중 결정.
- **느슨한 계약 보완**: MasterSchema 전부 Optional → 필요한 경계(DB 저장·응답)에 완성 가드를 둘지 결정.
- **`verify.py` 응답 모델**: `VerifyResponse` 등 미사용 — 응답 형식 확정 시 정리·배선 (현재는 `model_dump()` 원형 전송).
- **§1~3 ↔ runtime.py 드리프트**: 일부 필드(evidence `period_value`/`kosis_url`/`kosis_tbl_name` vs 구현 `period`/`url`/`table_name`, verification 구조)가 어긋남 → 정합화.
- **HITL / calculation / explanation**: 도메인 모델 없음. 기능 구체화 시 추가.
