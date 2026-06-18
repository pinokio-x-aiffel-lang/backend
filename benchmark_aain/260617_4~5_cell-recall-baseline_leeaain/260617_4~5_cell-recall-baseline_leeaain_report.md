# 260617_4~5_cell-recall-baseline_leeaain

## 1. 개요
1단계(itmId LLM 폴백) 도입 **전** 기준선. 캡처된 stage 4 후보 top-N 을 고정 주입하고 **stage 5(fetch_kosis_data)만 재실행**해, 셀 좌표 해소(itmId/objL)가 KOSIS 공식값을 재현하는 비율을 잰다. stage 4 검색 drift 를 배제해 itmId 수정 전후 비교를 깨끗하게 한다.

## 2. 무엇을 테스트했나
- 소스: `260614_source_from_origin_for_fetch_kosis_data.jsonl`
- 채점 대상: **T 행 (gold.value_source == "figure")** — 독립 정답값.
  F/M 의 gold.value 는 live_capture(순환참조)라 제외; 독립 정답값은 병인님 xlsx 에서 백필 예정(Task#2).
- 값 일치: 단위(만/천/억) 보정 후 상대오차 ≤2%. 시점은 KOSIS PRD_DE 정규화 비교.

## 3. 지표 결과
- 채점 행: 160 = 절대값형 **55** + 증감형(제외) 105  (evidence 확보 44, 에러 0)
- **절대값 recall: 0.236 (13/55)**  ← 주지표 (itmId 수정 전 기준선)
- 절대값+시점 recall: 0.200 (11/55)
- 증감형 적중: 1/105 — 절대조회로 재현 불가(거의 0이 정상)
- gold_tbl_id 자동시드(값 적중행): **13건** → Task#2 입력
- sanity: 캡처 당시 consistency_flag = {mismatch 32, no_evidence 115, ok 13}. 신규 재현 적중 13 ≈ 캡처 ok 13 → 채점기 일관.

### 3.1 실패 분해 (절대값형 55건)
| 결과 | 건수 | 비중 | 의미 |
|---|---|---|---|
| ✅ 값 적중 | 13 | 24% | 셀 정상 해소 |
| ⚠️ evidence 있는데 값 틀림 | 11 | 20% | 잘못된 셀/표 또는 합계폴백(이 중 population_fallback 4) |
| ❌ evidence 아예 없음 | 31 | **56%** | 후보 표에서 **셀 좌표 해소 실패**(itmId/objL) 또는 정답표 부재 |

**최대 누수 = evidence 0건(31/55, 56%).** itmId 가 결정적 문자열매칭만이라(LLM 폴백 없음, `map_claim_to_cell.py:146`) 항목명 불일치 시 즉시 None→무증거. → **1단계(itmId LLM 폴백)의 주 타깃.**

## 4. 주요 발견 / 시사점
1. **itmId 해소가 1순위 병목 (예상 확증).** 무증거 31건은 대부분 itmId 결정적매칭 실패로 추정 → 닫힌보기 LLM 폴백(population 에 이미 있는 `_llm_axis_matcher` 패턴)을 항목축에 도입하면 직접 공략 가능.
2. **T-figure 의 66%(105/160)가 증감형.** 절대 셀조회로는 원천적으로 재현 불가 — 2시점 조회+그룹연산(7단계 calculate_metric) 미배선 갭. itmId 와 **별개의 큰 누수**라 따로 추적 필요.

## 5. stage 4 표 recall (예비 — gold_tbl_id 진단셋)
- 진단셋: `benchmark_aain/build_gold_tbl_id.py` → `data/260617_gold_tbl_id_subset.jsonl` (74건 = 자동시드14 + 병인님60).
- 정답표가 현 stage4 후보 top-N 안에 있는 비율(in_pool): 신뢰행(high) 기준 **14/15**. 전체 78%는 자동resolve 노이즈 섞여 과신 금지.
- ⚠️ **표명→tbl_id 자동 resolve 는 신뢰 29 / 검수필요 45.** 키워드검색이 전국집계 대신 시도/세부표를 올림 — 이것이 **stage4 검색의 약점 그 자체**(예: `자살 사망자 수`→`인구십만명당 자살률`). 정밀 stage4 recall 은 45건 검수(또는 공식값-검증 패스) 후 확정.

## 6. 한계 / 범위
- 후보 top-N 고정(stage 4 재검색 생략) → 정답표가 후보에 없던 행은 구조적 miss. 표 recall vs 셀 precision 분리는 gold_tbl_id 완성(Task#2) 후 측정.
- 증감형 분류는 휴리스틱(`_DELTA_KW` + 음수값) — 발행 등락률(예: 소비자물가 전년비)을 과분류할 수 있음. gold_tbl_id 라벨 후 정밀화.
- 값 적중이 '우연히 다른 표 동일값'일 가능성(드묾) → gold_tbl_id 검수로 보강.
- T 행만 독립 채점. F/M 독립 정답값은 병인님 xlsx 백필(Task#2), NEI 는 범위 밖.