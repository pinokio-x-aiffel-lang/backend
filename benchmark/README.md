# benchmark — 평가 프레임 (성능 평가 · 개선 전후 비교)

> **무엇을 측정할지 정할 때 이 파일을 먼저 본다.** 목표 = 단계 성능 평가 + 개선 전후 비교.
> 폴더·파일 네이밍·결과 저장 규칙은 `test-convention` 스킬을 따른다.

## 측정 원칙 (린)
- **지금 개선하는 것의 임계경로 + 최종 결과(E2E)만 매 사이클 측정.** 나머지는 "그 단계를 건드릴 때만" 켜는 가드.
- 매 사이클 10단계를 다 재는 건 과하다. 측정 투자는 **현재 병목(4·5) + E2E**에 집중.
- 현 병목 = 4 retrieve · 5 fetch (KOSIS 조회). 7~10은 evidence가 ~0.8%만 도달해 단독 측정은 노이즈.

## 측정 결정표

| 구분 | 측정 대상 | 1차 지표 | 메모 |
|---|---|---|---|
| **활성** (매 사이클) | **E2E** | value-recall(절대 T) · non-NEI precision · coverage | "개선됐나"의 답. verdict macro-F1은 제품·후행 지표(4·5 개선돼야 움직임) |
| **활성** | **4 retrieve** | **Recall@N** | 정답표가 KOSIS에 아예 없음 = 기권으로 분리. gold_tbl_id 라벨 의존 |
| **활성** | **5 fetch** | **precision-when-found · coverage** (gold-table-in-pool 조건부) | 4단계와 분리해 측정. itmId/축/시점 서브분해는 *진단할 때만* |
| 가드 (건드릴 때만) | 2 extract · 3 normalize · 6 rank | 각자 기존 지표 | 평소 **상류 고정**, 그 단계 수정 시에만 재측정. (3 normalize는 delta 배선 시 재활성) |
| 가드 | 9 decide_verdict | exact-match (오차 0) | 결정적 — 스펙 건드릴 때만 (회귀 가드) |
| **제거** | 7 calc_metric · 8 check_alignment · 10 generate_explanation | — | evidence 0.8%만 도달 = 점추정 노이즈. **E2E verdict로 대체** |

**참고 지표(단독 측정 시):** 2=P·R·F1 / 3=value·period accuracy + 유형 분해 / 6=Top-1 acc·Δ vs RANK / 7=macro-F1+혼동행렬 / 8=M-F1.

## 공통 가드 (전후 비교의 전제 — 빼면 숫자를 못 믿는다)

1. **비결정성 통제** — LLM·live KOSIS라 단일 런 delta는 노이즈(회귀로 오인 실측). 상류 단계 고정(추출 공유·후보 주입) + n-run≥3 평균 or 시드 + **전후 같은 스코어러** + sanity 재현(예: gold 분류 수 동일).
2. **KOSIS 드리프트 분리** — 소스가 움직이는 표적(표 개정·값 수정). 측정 시점 기록 + "코드 회귀 vs 데이터 변동" 구분.
3. **표본수·CI** — 모든 율에 n 명시, n<~20은 "참고". 단일 런 점추정 단정 금지. (metrics: wilson_ci · 전후 유의성 mcnemar)
4. **유형 분리** — 절대 vs 증감(claim의 ~66%)을 3·5·7에서 분리 집계. 증감은 절대 셀조회로 재현 불가 → 안 나누면 지표 호도.

## 현재 활성 집합 = E2E · 4 retrieve · 5 fetch + 공통 가드
이게 "4·5 RAG 성능 평가"의 최소 충분 집합. 더 줄이면 4 vs 5 원인 추적이 끊긴다(바닥).

## 평가셋 · 스파인 (자산)
> 경로는 진행 중인 benchmark 재구성(per-stage `benchmark/<N_stage>/`)으로 이동 중 — 마이그레이션 확정 후 갱신.

| 용도 | 위치 |
|---|---|
| 5단계 cell-recall 베이스라인·스코어러 | `…/4~5_cell-recall-baseline_leeaain/` |
| gold_tbl_id 진단셋(74: 신뢰 29 / 검수 45) | `…/260617_gold_tbl_id_subset.jsonl` |
| 3단계 normalize gold(100) | `…/data/3_normalize_claim_100_gold.jsonl` |
| 2~5 gold-figure(123, 전부 True) | `…/2~6_from_labeled_true_source.jsonl` |
| 마스터 스파인 SSOT(213, 사람검수 gold_figures) | `…/data/260614_master_eval_213_parsed_human_checked_SSOT.jsonl` |

## 측정 시 체크리스트
1. 이 표에서 **활성 지표**만 잰다(가드/제거는 건드릴 때만).
2. **공통 가드 4축**을 적용한다(특히 상류 고정 + 같은 스코어러).
3. 절대 vs 증감 **유형을 분리**한다.
4. 결과는 `test-convention`(공유 하니스) 규칙으로 저장한다.
