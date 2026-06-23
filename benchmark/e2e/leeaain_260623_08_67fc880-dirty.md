# 단계별 성능 통합표 (현 HEAD)

### 개요
단계별 통합표(2~9), 현 HEAD. 3·5·6·7·8=260623 cascade 재채점, 2·4·9=격리/value-recall.

### 테스트 방법
STAGE_SCORERS·save_result.

### 성능 수치
| 단계 | 1차 지표 | 방법 | 평가 |
|---|---|---|---|
| 2 claim | 문장 F1 0.959 (P 0.983·R 0.937) · ctype 0.551 | 격리(LLM) | ✅ 추출 양호 / ⚠️ 유형분류 약함 |
| 3 normalize | value 0.955 · period 0.238 | cascade | ❌ period 약함 (n=22) |
| 4 retrieve | Recall@10 0.350 · @1 0.128 · MRR 0.210 | value-recall | ❌ 정답표 65% 놓침 |
| 5 fetch | coverage 0.498 · 셀값 0.411 | cascade | ❌ 실효 정답셀 ≈ 0.20 |
| 6 rank | Top-1 0.516 | cascade | △ 보통, n=31 작음 |
| 7 metric | macro-F1 0.560 · recall[T] 0.154·F 0.667·N 1.000 | cascade | ⚠️ 0.337→0.56 개선, 상류 cascade 영향 |
| 8 alignment | M-recall 0.459 (M-precision 0.944·M-F1 0.618) | cascade | ✅ 0→0.46 회복 (precision 0.94) |
| 9 verdict | exact-match 1.000 | 격리(결정적) | ✅ 산식 정확 |

### 분석
_(작성 필요)_

### 개선 전후 비교
_(작성 필요)_

### 한계·주의
_(작성 필요)_
