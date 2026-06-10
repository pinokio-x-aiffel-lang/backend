# 파이프라인 1~10단계 입출력 스키마

> 대상: `src/modules/` 의 10개 단계 함수(`src/pipeline/runner.py` 조립 순서).
> 경로는 `master_schema.…` 기준, 타입은 `src/schemas/runtime.py` 정의.
> 단계 번호는 `src/pipeline/runner.py`(10단계) 기준.

### 설계 결정 (흐름)
- **MasterSchema 하나**를 만들어 단계들이 차례로 채운다(직접 흐름). 각 함수 시그니처는 `(master_schema) -> None`(제자리 변경), 실패 시 raise → runner 가 `StepEvent(error)` 로 변환·중단.
- **1~5단계 = 수집**(`article → claims → analysis`), **7~10단계 = 판단**(`verifications`).
- **6단계는 현재 no-op**(빈 껍데기), **7단계가 `verifications` 를 생성**한다.
- 조인 키: `claim_id` 로 `claims[*]` ↔ `analysis[*]` ↔ `verifications.claim_results[*]` 를 묶는다.

### 공용 enum (`runtime.py`)
- `Verdict`: `T`(일치) · `F`(불일치=수치 자체를 잘못 인용, **확정 가짜**) · `M`(기사의 수치 오도/왜곡, 8단계만) · `N`(NEI=정보부족).
- `ClaimType`: `absolute`·`change_rate`·`ratio`·`distribution`·`comparison`·`metaphoric`·`verifiable`·`none`.
- `MismatchType`: `magnitude`·`rounding`·`direction`(수치 비교, 7단계) / `unit`·`period`·`population`·`subject`·`aggregation`(정합성, 8단계).
- `PeriodType`: `Y`·`M`·`Q`·`S`·`D`.
- `ValueSlot`: `raw`(본문 표기) / `llm_value`(정규화 표준값) / `is_inferred`.

---

### 1단계 `load_article` — 기사 내용 확인

#### 입력 (Reads)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `content` | str | 기사 URL 또는 본문 전문 |

#### 출력 (Writes)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `article` | `Article` | 적재된 기사 |
| `article.article_id` | str | 고정 `"art-0001"` |
| `article.content` | str | 본문 |
| `article.title` | str \| None | URL 입력 시만 추출 |
| `article.published_at` | str \| None | URL 입력 시 추출 / 본문 입력 시 더미 `"2025-04"` |
| `article.source` | str \| None | URL 입력 시만 |
| `article.url` | str \| None | URL 입력 시만 |

#### 동작 규칙
- 본문 텍스트 입력: 메타 없이 `content` 만 담는다(나머지 None). `published_at` 은 상대시점 계산 테스트용 더미 `"2025-04"`.
- URL 입력: 네이버·조선·아시아경제·뉴스타파·오마이뉴스는 사이트 전용 추출(`src/article/*`), 그 외엔 일반 JSON-LD/OG(`src/article/generic`).
- 실패 시 `LoadArticleError` raise.

---

### 2단계 `extract_statistical_claims` — 클레임 추출

#### 입력 (Reads)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `article.content` | str | 본문 |
| `article.article_id` | str | `claims[*].article_id` join 키 |

#### 출력 (Writes)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `claims` | list[`Claim`] | 추출된 주장 (NONE 포함) |
| `claims[*].claim_id` | str | `"clm-0001"` … 순번 |
| `claims[*].article_id` | str | `article.article_id` 참조 |
| `claims[*].sentence` | str | 주장 원문 문장 |
| `claims[*].claim_type` | `ClaimType` | absolute/…/none (유효치 아니면 NONE) |
| `claims[*].subject` | str | 측정 주제 (KOSIS 검색어) |
| `claims[*].value.raw` | str (`ValueSlot`) | 본문 수치 표기 그대로 |
| `claims[*].unit` | str | 단위 (`"%"`,`"시간"`,`"억원"`) |
| `claims[*].aggregation` | str | 고정 `"값"` |
| `claims[*].period_type` | `PeriodType` | Y/M/Q/S/D (유효치 아니면 `"Y"`) |
| `claims[*].period_value.raw` | str (`ValueSlot`) | 본문 시점 표기 그대로 |
| `claims[*].population` | str | 모집단 (`"청년"`,`"65세 이상"`) |
| `claims[*].cited_source` | str | 기사가 인용한 출처 |

#### 동작 규칙
- 이 단계는 `value.raw`/`period_value.raw` 만 채운다. `.llm_value` 는 빈 문자열로 두고 3단계가 채운다.
- `claim_type == NONE` 도 포함 — 필터링은 하류 분기 모듈 담당.
- 실패(LLM 호출/JSON 파싱) 시 `ExtractStatisticalClaimsError` raise.

---

### 3단계 `normalize_claim` — 한국어 수사 산술로 변환

#### 입력 (Reads)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `claims[*].value.raw` | str | 본문 수치 표기 |
| `claims[*].period_value.raw` | str | 본문 시점 표기 |
| `claims[*].compare_period_value.raw` | str \| None | 비교 시점 (있으면) |
| `article.published_at` | str | 상대시점 계산 기준(base) |

#### 출력 (Writes)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `claims[*].value.llm_value` | str | 표준 수치 (`"38.8"`,`"+3.0"`,`">=15"`,`"0.5"`) |
| `claims[*].period_value.llm_value` | str | 표준 시점 (`"2024"`,`"2024-01"`,`"2024-Q1"`,`"2024-H1"`) |
| `claims[*].compare_period_value.llm_value` | str | 비교 시점 표준값 (있으면) |

#### 동작 규칙
- 수치: 범위(`이상/이하/~`)·증감(`배/%증가`)·비율(`할푼리/대/분의/%`)·한국어 수사·일반 숫자 순으로 룰 적용.
- 시점: 절대표기(`YYYY년 M월`,`N분기`,`상/하반기`) 우선, 그 다음 `published_at` 기반 상대표기(`작년`,`지난달`,`전분기` 등).
- 룰 실패(None) 시 LLM 폴백, 그래도 실패면 원문(`raw`) 그대로 반환. 모든 claim·슬롯 병렬 처리.

---

### 4단계 `retrieve_kosis_candidates` — KOSIS 통계표 n개 찾기

#### 입력 (Reads)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `claims[*].claim_id` | str | `analysis[*].claim_id` join 키 |
| `claims[*].subject` | str | 검색 키워드 (국가 접두어·공백 제거) |

#### 출력 (Writes)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `analysis` | list[`ClaimAnalysis`] | claim별 1건 (순서 == claims 순서) |
| `analysis[*].claim_id` | str | claim 조인 키 |
| `analysis[*].kosis_search` | `KosisSearch` | 통합검색 호출 로그 |
| `…kosis_search.hits` | int | 검색 히트 수 |
| `…kosis_search.selected_tbl_id` | str \| None | RANK 1위 임시 선정(5단계가 실제 선정) |
| `…kosis_search.success` | int | 1 성공 / 0 실패 |
| `…kosis_search.error_msg` | str \| None | 실패 사유 |
| `analysis[*].candidates` | list[`KosisCandidate`] | 상위 `TOP_N=10` 후보 풀 |
| `…candidates[*].(org_id/tbl_id/tbl_nm/stat_nm/prd_de)` | str | 후보 표 메타 |
| `analysis[*].kosis_query` | `KosisQuery` | placeholder(success=0) — 5단계가 채움 |

#### 동작 규칙
- '가장 적합한 1개' 선정은 안 함 — 수집만 하고 RANK 1위를 `selected_tbl_id` 에 임시로 둬 5단계가 동작하게 한다.
- 한 claim 검색 실패(KosisError/ValueError)는 `success=0`+`error_msg` 로 기록하고 계속 진행(전체 중단 안 함).
- claim 간 검색은 `gather` 동시 호출(rate limit 은 공유 client 가 1000/min 강제).

---

### 5단계 `fetch_kosis_data` — KOSIS 셀 값 조회

#### 입력 (Reads)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `analysis[*].candidates` | list[`KosisCandidate`] | 후보 표 풀 |
| `claims[*].subject` / `.population` | str | 항목·분류축 매칭 대상 |
| `claims[*].period_type` / `.period_value.llm_value` | str | KOSIS PRD_DE 변환 |

#### 출력 (Writes)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `analysis[*].cell_attempts` | list[`CellAttempt`] | 후보 표별 조회 시도(디버깅: 항목·축·매칭 사유) |
| `analysis[*].kosis_query` | `KosisQuery` | 조회 로그(성공 시 `success=1`,`tbl_id`,params) |
| `analysis[*].evidence` | `Evidence` \| None | **선정 셀(공식 수치)**, 실패 시 None |
| `…evidence.value` | float \| None | KOSIS 공식 수치 |
| `…evidence.unit` / `.period` | str | KOSIS 응답값 그대로 |
| `…evidence.(kosis_org_id/kosis_tbl_id/kosis_item_id/table_name)` | str | 출처 메타 |
| `…evidence.classification` | dict | 분류축 매칭 필터 |
| `…evidence.population_fallback` | bool | 모집단 못 맞춰 '전체(합계)'로 대체 시 True |
| `…evidence.match_source` | str | `"rule"`(규칙+동의어) \| `"llm"`(폴백) |

#### 동작 규칙
- 2-pass: [1] 결정적(규칙+동의어)으로 후보 전체 동시 조회 → 모집단 특정값 얻으면 끝. [2] 못 얻었고 `population` 있으면 RANK 순 LLM 폴백 재조회(첫 성공에서 중단).
- 선정 우선순위: 모집단을 실제로 맞춘 표(비폴백) > 합계 폴백 표, 각 그룹 내 RANK 순.
- 한 claim 실패는 `kosis_query.success=0` 으로 기록하고 계속. claim 간·후보 표 간 모두 동시 조회.

---

### 6단계 `rank_evidence` — 증거 랭킹

#### 입력 (Reads)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `analysis` | list[`ClaimAnalysis`] | (의도) Evidence 후보 |

#### 출력 (Writes)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| — | — | (의도) 대표 Evidence 선정 |

#### 동작 규칙
- **현재 미구현 — 빈 껍데기(no-op, `return None`)**. happy-path 에서 아무것도 안 한다.
- 의도: claim 별 Evidence 후보를 적합도(기간·집계·단위 일치)로 정렬해 대표 증거 선정. (실제 선정은 5단계가 RANK·폴백 우선순위로 이미 수행.)

---

### 7단계 `calculate_metric` — 통계 수치 비교 판단 (Numeric Layer)

#### 입력 (Reads)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `claims[*].claim_id` | str | join 키 |
| `claims[*].claim_type` | `ClaimType` | 연산 유형 분기 |
| `claims[*].value.llm_value` | str (`ValueSlot`) | 정규화 주장 수치 `"38.8"`,`"+3.0"` |
| `claims[*].unit` | str | 주장 단위 `"%"`,`"시간"`,`"억원"` (단위 환산용) |
| `claims[*].period_value.llm_value` | str (`ValueSlot`) | 정규화 시점 (연도 불일치 판정용) |
| `analysis[*].evidence` | `Evidence` \| None | 선정 셀(없으면 None) |
| `analysis[*].evidence.value` | float \| None | KOSIS 공식 수치 |
| `analysis[*].evidence.unit` / `.period` / `.population_fallback` | str / str / bool | 단위·기간·전체대체 여부 |

#### 출력 (Writes)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `verifications` | `Verifications` | **신규 생성**(summary는 placeholder, 9단계서 확정) |
| `verifications.claim_results[*]` | `ClaimResult` | claim당 1건 |
| `…claim_results[*].metric` | `MetricResult` | 비교 결과 |
| `…metric.verdict` | `Verdict` | **T / F / N** (M 없음) |
| `…metric.claim_value` / `.kosis_value` / `.rel_diff` / `.within_tolerance` | float/float/float/bool | 비교 수치 |
| `…metric.mismatch_type` | `MismatchType` \| None | F 사유(magnitude/rounding/period) |
| `…metric.note` | str \| None | 계산 비고(단위환산·폴백·비교불가) |
| `…claim_results[*].verdict`/`.claim_value`/`.kosis_value`/`.evidence` | str/str/str/list | 표시 시드(미러) |

#### 판정 규칙
- `ABSOLUTE`/`VERIFIABLE` + 단일수치(SCALAR) 만 직접비교(`compute_absolute`). 허용오차 `tol = 0.5×10^(−소수자릿수)`.
- 내→**T**, 밖→**F**(연도 다름=period · 소폭 초과=rounding · 그 외=magnitude).
- 단위 비교불가(incompatible/unknown_unit/`%p`)·비스칼라·그룹연산 미배선·무증거·metaphoric/none → **NEI(N)**.
- `population_fallback` 이어도 수치로 T/F 만 내고, 오도 여부는 8단계가 판단(T인 경우).

---

### 8단계 `check_alignment` — 통계수치와 문장의 정합성 판단

#### 입력 (Reads)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `verifications.claim_results[*].metric.verdict` | `Verdict` | **T인 건만** 대상 |
| `claims[*].sentence`/`.subject`/`.population`/`.unit`/`.aggregation`/`.period_value.llm_value` | str | 기사 주장 |
| `analysis[*].evidence.subject`/`.population`/`.unit`/`.period`/`.table_name`/`.population_fallback` | str/… | KOSIS 수치가 나타내는 바 |

#### 출력 (Writes) — `metric` in-place 보정 (verifications)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `…claim_results[*].metric.verdict` | `Verdict` | 해석 일치→**T** / 오도·왜곡→**M** / LLM실패→**N** |
| `…claim_results[*].metric.mismatch_type` | `MismatchType` | 오도/왜곡 차원(population/subject/aggregation/unit/period) |
| `…claim_results[*].metric.align_reason` | str | 판정 근거(LLM reason / 실패 사유) |
| `…claim_results[*].metric.align_source` | str | `"llm"` \| `"llm_failed"` |
| `…claim_results[*].verdict`/`.mismatch_type` | str | 미러(표시·하위호환) |

#### 판정 규칙
- 대상: `metric.verdict == T` 인 claim_result 만 LLM 호출. **F/NEI 는 통과**(손대지 않음).
- LLM(`HCX-007` structured) → `{aligned, dimension, reason}`. `aligned=true`→T 유지, `aligned=false`→**M**+dimension 기록, 개별 LLM 실패→**NEI**(`align_source="llm_failed"`).
- **M 은 이 단계에서만 생성**. analysis 에서 읽고 verifications 에 쓴다(수집/판단 분리).

---

### 9단계 `decide_verdict` — 종합 분석·검증 결과 생성

#### 입력 (Reads)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `verifications.claim_results[*].metric.verdict` / `.mismatch_type` | `Verdict`/`MismatchType` | 7~8단계 판정 |

#### 출력 (Writes)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `…claim_results[*].verdict` | str | `metric.verdict` 확정 미러 |
| `…claim_results[*].mismatch_type` | str | `metric.mismatch_type` 미러 |
| `verifications.summary.total_claims` | int | claim 수 |
| `verifications.summary.overall_verdict` | str | claim별 verdict 중 최악(심각도 F>M>N>T) |
| `verifications.summary.average_confidence` | float | 현재 `0.0`(TODO) |

#### 판정 규칙
- `verifications` 가 없으면(7단계 미실행 등 예외 경로) `claims` 로 최소 골격 생성(레거시 폴백).
- `overall_verdict` = claim별 verdict 중 심각도(`F:3 > M:2 > N:1 > T:0`) 최고값. 비면 `UNVERIFIED`.
- 현재는 전이 구현 — `confidence`(rel_diff→[0,1])·`verdict_human`·`llm_model` 정밀 산출은 TODO.

---

### 10단계 `generate_explanation` — 설명 생성

#### 입력 (Reads)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `verifications.claim_results[*].verdict` | str | T/F/M/그외 분기 |
| `…claim_results[*].claim_value` / `.kosis_value` | str | 주장값·공식값 |
| `…claim_results[*].evidence[0].table_name` | str \| None | 출처 표기 |
| `claims[*].subject` / `.unit` / `.period_type` / `.period_value.llm_value` | str | 문장 구성 요소 |

#### 출력 (Writes)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `…claim_results[*].explanation` | str | 한국어 설명문 |

#### 동작 규칙
- 템플릿(조사 `은/는` 자동, 기간 한국어 변환):
  - `T`: "…KOSIS 공식 수치와 일치합니다."
  - `F`: "…KOSIS 공식 수치(X)와 다릅니다. 불일치 유형: …."
  - `M`: "…KOSIS 공식 수치(X)와 부분적으로 일치합니다."
  - `N`/`UNVERIFIED`/기타: "…KOSIS 공식 통계를 찾지 못해 검증할 수 없습니다."
- `verifications` 가 None 이면 no-op.

