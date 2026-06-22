# leeaain_260622_01_ddab1c1-dirty — [7] calculate_metric 성능 평가

### 개요
7단계 calculate_metric — #2(population fallback NEI 해제)·#3(range 포함비교) 전후.

### 테스트 방법
after6 동결 캡처에 calculate_metric 재실행(결정적, LLM 무). 7_source_2 scorable gold_verdict_stage7 대조. BEFORE=#2/#3 적용 전 커밋(동일 scorer 실측).

### 성능 수치
| 지표 | 방법 | before | after |
|---|---|---|---|
| macro-F1 | frozen-capture(after6 고정) | 0.424 | 0.476 |
| recall[T] | frozen-capture(after6 고정) | 0.051 (2/39) | 0.051 (2/39) |
| recall[F] | frozen-capture(after6 고정) | 0.389 (14/36) | 0.583 (21/36) |
| recall[N] | frozen-capture(after6 고정) | 1.000 (51/51) | 1.000 (51/51) |

### 분석
#3: 수치 범위/부등(>=89·<75 등) 절대형을 포함비교로 살림(F +2). #2: 모집단 전부폴백을 NEI 로 막던 정책 해제→전체값과 T/F(F +5), 8단계가 모집단 M 판정. recall[T] 불변은 남은 T-killer가 #1(증감, 상류 미추출)이라서.

### 개선 전후 비교
macro-F1 0.424→0.476; recall[F] 0.389 (14/36)→0.583 (21/36); recall[N] 무손상(폴백 해제가 N 오염 없음).

### 한계·주의
#1 증감(change_rate)은 미반영 — 원인이 7단계 아닌 상류(stage2 비교기준 미추출 115/185, stage3 compare_period 오정규화 24건)라 별도 작업·재실행 필요. range 부등호(>,>=)는 경계포함 근사.
