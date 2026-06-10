# 260610_7-8_check-alignment_leeaain

> 7·8단계(Numeric Layer + Check Alignment) 단위/흐름 테스트 결과 리포트.
> verdict 정책: **7=T/F/NEI**, **8=T만 재판정**(일치→T·오도/왜곡→M·LLM실패→NEI).
> 원자료: [`260610_7-8_check-alignment_leeaain.json`](260610_7-8_check-alignment_leeaain.json)

### 1. 테스트 목적
7단계(`calculate_metric`/numeric layer)가 주장 수치 ↔ KOSIS 공식 수치를 비교해
**T/F/NEI** 와 mismatch_type·허용오차를 산출하는지, 8단계(`check_alignment`)의 보정
로직(`apply_alignment`)이 T 건을 해석 일치→T·오도/왜곡→M·LLM실패→NEI 로 고치는지,
7→8→9→10 흐름에서 8단계 결과가 더미 없이 최종 출력까지 전달되는지 검증한다.

### 2. 검증 대상 모듈
- `src/numeric/value.py` — `parse_claim_value`
- `src/numeric/units.py` — `align_value`
- `src/numeric/compare.py` — `compute_absolute`, `tolerance_abs`
- `src/modules/calculate_metric.py` — `calculate_metric` (stage)
- `src/modules/check_alignment.py` — `apply_alignment` (순수 보정부)

### 3. 도구로만 쓰인 모듈 (검증대상 아님)
- `src/schemas/runtime.py` — Claim/Evidence/MetricResult 등 입력 구성용 스키마
- `src/kosis/units.py` — compare 가 단위환산을 재사용
- `src/modules/decide_verdict.py`, `src/modules/generate_explanation.py` — 흐름 통과 확인용(9·10단계), 검증 대상 아님

### 4. 테스트 일자 / 작성자
- 일자: 2026-06-10
- 작성자: leeaain

### 5. 결과  (원자료: `260610_7-8_check-alignment_leeaain.json`)
- 실행: `uv run pytest tests/test_numeric_value.py tests/260610_7_compare_leeaain.py tests/test_calculate_metric.py tests/test_check_alignment_apply.py tests/test_pipeline_7_to_10_flow.py -v`
- 비밀키 불필요(8단계 LLM `_judge` 는 mock 으로 대체)
- **총 25 · PASS 25 · FAIL 0 · SKIP 0** (1.39s)

| 파일 | 대상 | PASS/FAIL |
|---|---|---|
| `test_numeric_value.py` | `value.parse_claim_value` | 7 / 0 |
| `260610_7_compare_leeaain.py` | `compare.compute_absolute` | 10 / 0 |
| `test_calculate_metric.py` | `calculate_metric` stage | 3 / 0 |
| `test_check_alignment_apply.py` | `check_alignment.apply_alignment` | 4 / 0 |
| `test_pipeline_7_to_10_flow.py` | 7→8→9→10 흐름(통합) | 1 / 0 |

주요 확인 케이스:
- 7단계: 허용오차 내→**T**, 초과→**F**(magnitude/rounding/period), 단위 비교불가/`%p`/비스칼라/무증거/metaphoric→**NEI**, `population_fallback`→**T**(수치로만; 오도판단은 8단계), 단위환산(억원↔백만원).
- 8단계(`apply_alignment`): 해석 일치→**T 유지**, 오도/왜곡→**M**+차원, LLM 실패→**NEI**+근거(`align_reason`/`align_source`).
- 흐름: c1=T(8단계 mock 통과)·c2=F·c3=NEI(N) 가 9·10 통과 후에도 실제값 유지(더미 `(더미)`/`0.72`/`UNVERIFIED` 0건), `c1.metric.align_source=="llm"`.

### 6. 한계 / 범위 밖
- **`check_alignment` 실제 LLM 판정(`_judge`)은 라이브 미검증** — 흐름 테스트는 `_judge` 를 mock 으로 대체. 순수 보정부(`apply_alignment`)만 단위 테스트.
- 1~6단계(load~fetch)는 실행하지 않음 — 7단계 입력(구조화된 claim·evidence)을 합성으로 주입.
- 실제 KOSIS 조회·좌표해소는 범위 밖(별도: `260609_5_metadata_leeaain.py`).
