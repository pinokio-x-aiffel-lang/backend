# leeaain_260624_02_f4d9ef9-dirty — [6] rank_evidence 성능 평가

### 개요
6단계 rank_evidence **frozen-독립** 평가 — 후보 표 중 1위 선정 Top-1 accuracy.

### 테스트 방법
격리: 6_source_1(독립, gold_best_index) 의 claim·evidences 로 MasterSchema 구성 → rank_evidence 실행 → evidences[0] 의 원본 index==gold_best_index=top1_correct. 베이스라인=RANK 순(index 0). 캡처 아님 → stale·순환 무관.

### 성능 수치
| 지표 | 종류 | 값 | 95% CI |
|---|---|---|---|
| Top-1 accuracy | accuracy | 0.500 (10/20) | [0.299, 0.701] |
| 기권율 | abstain-rate | 0.000 (0/20) | [-0.000, 0.161] |
| Δ vs RANK 베이스라인 | delta | 0.200 | — |

### 분석
Top-1 = 주제적합 표를 1위로 올린 비율. Δ vs RANK = LLM 재정렬이 원순서 대비 얼마나 개선했나.

### 개선 전후 비교
_(작성 필요)_

### 한계·주의
기권(LLM null)은 모듈이 순서 유지로 흡수 → 기권율 미집계(0). scorable=gold_best_index 존재 행만. rank_evidence 는 값 미사용(주제 적합도만).
