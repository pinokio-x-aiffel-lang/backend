# 단계별 통합표 (실발행일)

### 개요
단계별 통합표 (실발행일)

### 테스트 방법
_(작성 필요)_

### 성능 수치
| 단계 | 1차 지표 | 방법 | 평가 |
|---|---|---|---|
| 2 claim | 문장 F1 0.959 (P 0.983·R 0.937) · ctype 0.551 | 격리(LLM) | ✅ 추출 양호 / ⚠️ 유형분류 약함 |
| 3 normalize | value 0.955 · period 0.714 | cascade | ✅ period 0.238→0.714 (실발행일) |
| 4 retrieve | Recall@10 0.350 · @1 0.128 · MRR 0.210 | value-recall | ❌ 정답표 65% 놓침 |
| 5 fetch | coverage 0.502 · 셀값 0.398 | cascade | ❌ 실효 정답셀 ≈ 0.20 |
| 6 rank | Top-1 0.516 | cascade | △ 보통, n=31 |
| 7 metric | macro-F1 0.602 · recall[T] 0.231·F 0.667·N 1.0 | cascade | ✅ 0.560→0.602, recall[T]↑(발행일 효과) |
| 8 alignment | M-recall 0.459 (M-precision 0.944·M-F1 0.618) | cascade | ✅ M 탐지 유지 |
| 9 verdict | exact-match 1.000 | 격리(결정적) | ✅ 산식 정확 |

### 분석
_(작성 필요)_

### 개선 전후 비교
_(작성 필요)_

### 한계·주의
_(작성 필요)_
