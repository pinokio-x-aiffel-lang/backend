# KOSIS API 연동 명세

> **대상 독자**: `src/kosis/` 를 사용·수정하는 백엔드 개발자
>
> **목적**: KOSIS OpenAPI 전체 스펙이 아니라, **우리 모듈(`src/kosis/`)이 실제로 보내는 요청 파라미터와 매핑해 사용하는 응답 필드**만 추려 명세한다. (예: `objL3~8` 빈 값 고정, `newEstPrdCnt` 미사용, 응답에서 `SearchHit`/`KosisCell` 필드만 추림.)
>
> **단일 진실 원천(SSOT)**: `src/kosis/` 의 코드. 본 문서와 코드가 불일치하면 코드가 우선하며, 본 문서는 즉시 갱신한다.
>   - 공유 HTTP 레이어: `src/kosis/client.py`
>   - 통합검색: `src/kosis/search.py`
>   - 구조 메타: `src/kosis/metadata.py`
>   - 셀 값 조회: `src/kosis/cell.py`
>
> **버전**: v1 · 마지막 갱신: 2026-06-08

---

## 0. 개요

우리 모듈은 KOSIS OpenAPI 중 **통계표 관련 3개 엔드포인트**만 사용한다.

| # | API (엔드포인트) | method | 용도 | 모듈 | 상수 |
|---|---|---|---|---|---|
| 1 | 통합검색 `statisticsSearch.do` | `getList` | 키워드 → **통계표 후보** 검색 | `search.py` | `SEARCH_URL` |
| 2 | 통계표 구조 메타 `statisticsData.do` | `getMeta` | 통계표의 **항목·분류축·시점·단위 등 구조 메타** | `metadata.py` | `META_URL` |
| 3 | 통계자료 `statisticsParameterData.do` | `getList` | 통계표의 **실제 값(셀) 조회** | `cell.py` | `DATA_URL` |

**전형적 흐름**: ① 검색(후보) → ② 메타(코드 확인) → ③ 자료(값 조회)

- 다음 단계로 넘기는 식별자: ① → `ORG_ID`+`TBL_ID`, ② → `itmId`/`objL`/`prdSe` 코드.
- 모든 호출은 공유 레이어 `client.kosis_get` 을 거쳐 Session 재사용·재시도·rate limit·`jsonVD=Y` 가 적용된다.

### 엔드포인트 상수 (`src/kosis/client.py`)

```python
DATA_URL   = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
SEARCH_URL = "https://kosis.kr/openapi/statisticsSearch.do"
META_URL   = "https://kosis.kr/openapi/statisticsData.do"  # getMeta(통계표 구조 메타)
```

> ⚠️ `statisticsData.do`(메타)와 이름이 비슷한 **`statisticsExplData.do`(통계설명, 긴 조사 설명문)** 는 별개 서비스이며 우리 모듈에서는 사용하지 않는다.

---

## 1. 공통 사항

### 1.1 자동 주입 파라미터

`client.kosis_get` 이 모든 요청에 강제로 주입한다 (**호출자 값이 우선**).

| 파라미터 | 값 | 이유 |
|---|---|---|
| `format` | `json` | JSON 응답 |
| `jsonVD` | `Y` | 값 내부 따옴표를 결정론적으로 처리. json5 관용 파싱(공개 MCP 방식)으로는 못 막음 → **항상 필수** |

### 1.2 인증키

- 모든 요청에 `apiKey` 필수.
- `resolve_api_key(api_key)`: 인자가 있으면 그대로, 없으면 `.env` 의 `KOSIS_API_KEY`.
- 둘 다 없으면 `ValueError`.

### 1.3 응답 정규화 / 에러 (`kosis_get`)

| 응답 형태 | 처리 |
|---|---|
| `list` | 그대로 반환 |
| `dict` + `err`/`errMsg` 포함 | `KosisError` (인증/요청 오류, fail-loud) |
| `dict` (오류 아님) | `require_list=True` 면 `KosisError`, 아니면 `[dict]` 로 감쌈 |

- KOSIS 는 **인증 실패 시 list 가 아닌 dict** 를 준다 → 데이터 조회(`call_kosis`)는 `require_list=True` 로 방어.
- HTTP 비정상·JSON 파싱 실패 시 지수 백오프로 재시도(기본 3회), 초과 시 `KosisError`.
- rate limit: 슬라이딩 윈도우 기반, 기본 900/min (KOSIS 한도 1000/min 대비 여유).

---

## 2. 요청 표

각 API 호출 시 보내는 파라미터. `format`/`jsonVD` 는 §1.1 이 자동 주입(호출자 값 우선).

### 2.1 통합검색 — `statisticsSearch.do` (method=`getList`)

모듈: `src/kosis/search.py` (`search_tables` / `search_tables_many`).

| 파라미터 | 값 / 예시 | 필수 | 설명 |
|---|---|:---:|---|
| `method` | `getList` | ✅ | 검색 목록 조회 |
| `apiKey` | KOSIS 인증키 | ✅ | `resolve_api_key()` |
| `searchNm` | 검색 키워드 | ✅ | `keyword.strip()` (빈 값이면 호출 없이 `[]`) |
| `startCount` | `1` | ✅ | 결과 시작 위치(페이징) |
| `resultCount` | `min(top_n, 1000)` | ✅ | 가져올 개수, **상한 1000** |
| `sort` | `RANK` / `DATE` | ✅ | 정확도순 / 최신순. 그 외 값은 `ValueError` |
| `format` | `json` | (자동) | §1.1 |
| `jsonVD` | `Y` | (자동) | §1.1 |

### 2.2 통계표 구조 메타 — `statisticsData.do` (method=`getMeta`)

모듈: `src/kosis/metadata.py` (`fetch_meta_item` / `fetch_table_meta`).

| 파라미터 | 값 / 예시 | 필수 | 설명 |
|---|---|:---:|---|
| `method` | `getMeta` | ✅ | 메타 조회 |
| `apiKey` | KOSIS 인증키 | ✅ | |
| `type` | 아래 8종 중 **1개** | ✅ | type당 1종만 반환(`type=ALL` 없음) → 필요한 type 순회 |
| `orgId` | 기관 ID | ✅ | |
| `tblId` | 통계표 ID | ✅ | |
| `format` | `json` | (자동) | §1.1 |
| `jsonVD` | `Y` | (자동) | §1.1 |

**`type` 코드 8종** (`META_ITEMS`)

| 코드 | 의미 |
|---|---|
| `TBL` | 통계표명칭 |
| `ORG` | 기관명칭 |
| `PRD` | 수록정보(시점) |
| `ITM` | 분류항목 |
| `CMMT` | 주석 |
| `UNIT` | 단위 |
| `SOURCE` | 출처 |
| `WGT` | 가중치 |

### 2.3 통계자료(셀 값) — `statisticsParameterData.do` (method=`getList`)

모듈: `src/kosis/cell.py` (`build_params(KosisQuery)`).

| 파라미터 | 값 / 예시 | 필수 | 설명 |
|---|---|:---:|---|
| `method` | `getList` | ✅ | 목록 조회 |
| `apiKey` | KOSIS 인증키 | ✅ | |
| `orgId` | 기관 ID | ✅ | |
| `tblId` | 통계표 ID | ✅ | |
| `itmId` | 항목 코드 | ✅ | 메타 `ITM` 에서 |
| `objL1` | 분류축1 코드 (기본 `ALL`) | ✅ | 메타에서 |
| `objL2` | 분류축2 코드 (기본 `ALL`) | ✅ | |
| `objL3`~`objL8` | `""` (빈 문자열) | ✅ | 미사용 축은 빈 값으로 고정 |
| `prdSe` | 시점 주기 (Y/M/Q 등) | ✅ | `query.period_se` |
| `startPrdDe` | 시점 | ✅ | `= period` (단일 시점은 start=end) |
| `endPrdDe` | 시점 | ✅ | `= period` |
| `format` | `json` | ✅ | build_params 에 명시(+ §1.1) |
| `jsonVD` | `Y` | ✅ | 동일 |

> `newEstPrdCnt`(최근 N기간 자동)는 **사용하지 않는다** — 과거 시점 검증에 부적합. 시점은 항상 `startPrdDe = endPrdDe` 로 명시.

---

## 3. 응답 표

각 API 가 돌려주는 필드와 우리 모듈의 매핑.

### 3.1 통합검색 → `SearchHit`

통계표 객체의 list (`statisticsSearch.do` 고정 스키마). `SearchHit` 로 추려 매핑한다.

| 응답 필드 | `SearchHit` | 설명 |
|---|---|---|
| `ORG_ID` | `org_id` | 기관 ID |
| `TBL_ID` | `tbl_id` | 통계표 ID |
| `TBL_NM` | `tbl_nm` | 통계표명 |
| `ORG_NM` | `org_nm` | 기관명 |
| `STAT_NM` | `stat_nm` | 통계(조사)명 |
| `STRT_PRD_DE` + `END_PRD_DE` | `prd_de` | 수록 기간 (`STRT~END` 로 합침) |
| `FULL_PATH_ID` | `prd_de` 대체 | 위 두 기간이 모두 비면 `prd_de` 대체값 |
| (원본 dict 전체) | `raw` | 필요 시 참조 |

**주의**
- 이 엔드포인트에는 단일 `PRD_DE` 필드가 **없다** → 수록 기간은 `STRT_PRD_DE~END_PRD_DE` 로 구성.
- 결과는 `top_n` 개로 잘라 반환(`[:top_n]`).
- 다음 단계(메타·셀)에 넘기는 식별자: `ORG_ID` + `TBL_ID`.

### 3.2 통계표 구조 메타 (getMeta) — 원본 보관

getMeta 응답은 `type` 마다 필드 구성이 다르며, 우리 코드는 **매핑 없이 원본을 보관**한다.

- `type` 별 응답(list 또는 dict)을 `TableMeta.items[type]` 에 그대로 저장(파싱하지 않음).
- `ITM`(항목 코드/명) · `PRD`(시점) · `UNIT`(단위) 등이 다음 단계 셀 조회의 `itmId` · `objL` · `prdSe` 값 출처.
- `fetch_table_meta` 는 `meta_types=None` 이면 8종 전체를 순회.
- **type별 실패는 예외로 던지지 않고** `TableMeta.errors[type]` 에 메시지를 모아두고 나머지 type 을 계속 진행한다.

```python
@dataclass
class TableMeta:
    org_id: str
    tbl_id: str
    items: dict[str, Any]   # type → getMeta 응답 (성공한 type 만)
    errors: dict[str, str]  # type → 에러 메시지 (빈/오류 응답 type)
```

**응답 row 필드** — 아래는 우리 파이프라인이 실제로 참조하는 필드만 정리한 것 (✅ = 코드/테스트에서 확인).

`type=ITM` (셀 좌표 코드의 출처 — 가장 중요). row 한 건은 한 분류(축)의 한 값(항목 또는 분류값).

| 필드 | 확인 | 설명 | 다음 단계 매핑 |
|---|:---:|---|---|
| `OBJ_ID` | | 분류(축) ID | `objL{n}` 축 식별 |
| `OBJ_NM` | ✅ | 분류(축)명 (예: `항목`, `성별`, `연령`) | `OBJ_NM=="항목"` 인 행의 `ITM_ID` 가 `itmId` |
| `ITM_ID` | ✅ | 항목/분류값 코드 | `itmId` 또는 `objL` 코드값 |
| `ITM_NM` | ✅ | 항목/분류값 명 | 사람이 읽는 이름 |

`type=TBL`

| 필드 | 확인 | 설명 |
|---|:---:|---|
| `TBL_NM` | ✅ | 통계표명 |

그 외 type (`ORG`/`PRD`/`CMMT`/`UNIT`/`SOURCE`/`WGT`) — 우리 코드가 특정 필드를 매핑하지 않으므로 원본 응답을 그대로 사용한다. 필드 구성은 type별 raw 응답을 직접 확인할 것 (필요해지면 본 표에 추가).

### 3.3 통계자료 → `KosisCell`

row dict 의 list. `to_cell` 이 `KosisCell` 로 매핑.

| 응답 필드 | `KosisCell` | 설명 |
|---|---|---|
| `PRD_DE` | `period` | 시점 |
| `DT` | `value` | 값. KOSIS 가 문자열로 주므로 `float` 변환 (실패 시 `ValueError`) |
| `DT` (원문) | `value_raw` | 변환 전 문자열 |
| `UNIT_NM` | `unit` | 단위 |
| `LST_CHN_DE` | `lst_chn_de` | 최종 변경일 |
| `C1`/`C2`/… (+ `_NM`) | (매칭용) | 분류 코드 컬럼. 셀 선택에 사용 |
| (원본 row) | `raw` | 필요 시 참조 |

**셀 매칭 규칙 (`find_cell_row`)**
- 조건: `PRD_DE == period` **AND** `match_filters` 의 모든 키에서 `row[k] == v`.
- `_NM`(이름)이 아닌 **코드값으로 `==` 정확 일치** → substring 함정 회피.
  - 예: `match_filters = {"C1": "10", "C2": "00"}` → C1 코드 `10`, C2 코드 `00` 인 셀.
- 매칭 0건이면 `None` (= `fetch_cell` 반환값 `None`).
- 데이터 조회는 항상 list 응답이어야 하므로 `call_kosis` 가 `require_list=True` — dict(인증 실패 등) 응답 시 `KosisError`.

---

## 부록 A. 호출 흐름 요약

```
[키워드]
   │  search_tables (statisticsSearch.do, getList)
   ▼
SearchHit(org_id, tbl_id, ...)            ← 통계표 후보 상위 N개
   │  fetch_table_meta (statisticsData.do, getMeta · type별)
   ▼
TableMeta(items: ITM/PRD/UNIT/...)        ← itmId/objL/prdSe 코드 확보
   │  fetch_cell (statisticsParameterData.do, getList)
   ▼
KosisCell(period, value, unit, ...)       ← 실제 값 한 셀
```
