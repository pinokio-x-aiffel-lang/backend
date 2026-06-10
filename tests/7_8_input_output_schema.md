# 7·8단계 입출력 스키마 (Numeric Layer · Check Alignment)

> 대상: `src/modules/calculate_metric.py`(7) · `src/modules/check_alignment.py`(8).
> 경로는 `master_schema.…` 기준, 타입은 `src/schemas/runtime.py` 정의.
> 단계 번호는 `src/pipeline/runner.py`(10단계) 기준.

## 설계 결정 (verdict 정책)
- **7단계는 T / F / NEI 만** 낸다. (M 없음)
  - **T** = 수치 허용오차 내 일치 · **F** = 불일치(=수치 자체를 잘못 인용, **확정 가짜**) · **NEI** = 정보부족(비교 불가)
- **F·NEI 는 8단계를 통과**(손대지 않음). **T 만** 8단계로 간다.
- **8단계는 T 건의 '해석'을 재판정**: 기사 주장이 수치를 오도/강한 왜곡 없이 전달 → **T 유지**, 오도/왜곡 → **M**, LLM 실패 → **NEI(근거 기록)**.
- **M 은 8단계만 생성.** `metric` 은 `ClaimResult`(verifications)에 있고, 8단계는 **analysis 에서 읽고 verifications 에 쓴다**(수집/판단 분리).
- 조인 키: `claim_id` 로 `claim_results[*]` ↔ `claims[*]` ↔ `analysis[*].evidence`.

## 공용 enum (`runtime.py`)
- `Verdict`: `T`(일치) · `F`(불일치=확정 가짜) · `M`(기사의 수치 오도/왜곡, 8단계만) · `N`(NEI=정보부족; 무증거·비교불가·검증대상아님·정합성판정실패)
- `MismatchType`: `magnitude`·`rounding`·`period`(7단계 F 사유) / `unit`·`population`·`subject`·`aggregation`·`period`(8단계 오도/왜곡 차원)

---

## 7단계 `calculate_metric` (Numeric Layer)

### 입력 (Reads)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `claims[*].claim_id` | str | join 키 |
| `claims[*].claim_type` | `ClaimType`(enum) | absolute/change_rate/…/none |
| `claims[*].value.llm_value` | str (`ValueSlot`) | 정규화 주장 수치 `"38.8"`,`"+3.0"` |
| `claims[*].unit` | str | 주장 단위 `"%"`,`"시간"`,`"억원"` |
| `claims[*].period_value.llm_value` | str (`ValueSlot`) | 정규화 시점 |
| `analysis[*].evidence` | `Evidence \| None` | 선정 셀(없으면 None) |
| `analysis[*].evidence.value` | float \| None | KOSIS 공식 수치 |
| `analysis[*].evidence.unit` / `.period` / `.population_fallback` | str / str / bool | 단위·기간·전체대체 여부 |

### 출력 (Writes)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `verifications` | `Verifications` | 스켈레톤 생성(summary는 placeholder, 9단계서 확정) |
| `verifications.claim_results[*]` | `ClaimResult` | claim당 1건 |
| `…claim_results[*].metric` | `MetricResult` | 비교 결과 |
| `…metric.verdict` | `Verdict` | **T / F / NEI** (M 없음) |
| `…metric.claim_value` / `.kosis_value` / `.rel_diff` / `.within_tolerance` | float/float/float/bool | 비교 수치 |
| `…metric.mismatch_type` | `MismatchType` \| None | F 사유(magnitude/rounding/period) |
| `…metric.note` | str \| None | 계산 비고(단위환산·폴백·비교불가) |
| `…claim_results[*].verdict`/`.claim_value`/`.kosis_value`/`.evidence` | str/str/str/list | 표시 시드(미러) |

### 판정 규칙
- `ABSOLUTE`/`VERIFIABLE` + 단일수치(SCALAR) 만 직접비교. 허용오차 `tol=0.5×10^(−소수자릿수)`.
- 내→**T**, 밖→**F**(연도 다름=period, 소폭 초과=rounding, 그 외=magnitude).
- 단위 비교불가(incompatible/unknown/`%p`)·비스칼라·그룹연산 미배선·무증거·metaphoric/none → **NEI**.
- `population_fallback` → **수치로 T/F 만** 내고(강제 M 없음), 오도 여부는 8단계가 판단(T인 경우).

---

## 8단계 `check_alignment`

### 입력 (Reads)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `verifications.claim_results[*].metric.verdict` | `Verdict` | **T인 건만** 대상 |
| `claims[*].sentence`/`.subject`/`.population`/`.unit`/`.aggregation`/`.period_value.llm_value` | str | 기사 주장 |
| `analysis[*].evidence.subject`/`.population`/`.unit`/`.period`/`.table_name`/`.population_fallback` | str/… | KOSIS 수치가 나타내는 바 |

### 출력 (Writes) — `metric` in-place 보정 (verifications)
| 경로 | 타입 | 담기는 것 |
|---|---|---|
| `…claim_results[*].metric.verdict` | `Verdict` | 해석 일치→**T** / 오도·왜곡→**M** / LLM실패→**NEI** |
| `…claim_results[*].metric.mismatch_type` | `MismatchType` | 오도/왜곡 차원(population/subject/aggregation/unit/period) |
| `…claim_results[*].metric.align_reason` | str | 판정 근거(LLM reason / 실패 사유) |
| `…claim_results[*].metric.align_source` | str | `"llm"` \| `"llm_failed"` |
| `…claim_results[*].verdict`/`.mismatch_type` | str | 미러(표시·하위호환) |

### 판정 규칙
- 대상: `metric.verdict == T` 인 claim_result 만 LLM 호출. **F/NEI 는 통과**.
- LLM(`HCX-007` structured): "기사 주장이 수치를 오도/강한 왜곡 없이 전달했나" → `{aligned, dimension, reason}`.
- `aligned=true` → T 유지(`align_source="llm"`).
- `aligned=false` → M + `dimension`을 `mismatch_type` 기록(`align_source="llm"`).
- LLM 실패 → NEI + `align_reason="정합성 LLM 판정 실패"`, `align_source="llm_failed"`.
