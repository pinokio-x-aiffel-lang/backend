# 단계별 성능 통합표 (2~9) — 현재(2c5fa86)

### 개요
파이프라인 단계별 성능 통합표(2~9), 현재 코드(2c5fa86 포함). 고정 SSOT 213기사.

### 테스트 방법
3·5·6·7·8=260623 캡처(2c5fa86) cascade 재채점. 2 claim·4 retrieve·9 verdict=격리/value-recall(2c5fa86 무관 → 260623_01 재사용). 채점=STAGE_SCORERS, 저장=save_result.

### 성능 수치
| 단계 | 1차 지표 | 방법 | 평가 |
|---|---|---|---|
| 2 claim | 문장 F1 0.959 (P 0.983·R 0.937) · claim_type acc 0.551 | 격리(LLM) | ✅ 추출 양호 / ⚠️ 유형분류 약함 |
| 3 normalize | value 0.955 · period 0.238 | cascade | ❌ period 약함 (value n=22) |
| 4 retrieve | Recall@10 0.350 · @1 0.128 · MRR 0.210 | value-recall | ❌ 정답표 65% 놓침 |
| 5 fetch | coverage 0.498 · 셀값 0.411 | cascade | ❌ 실효 정답셀 ≈ 0.20 |
| 6 rank | Top-1 0.516 | cascade | △ 보통, n=31 작음 |
| 7 metric | macro-F1 0.560 · recall[T] 0.154·F 0.667·N 1.0 | cascade | ⚠️ 0.506→0.560 개선(2c5fa86), 상류 cascade 영향 |
| 8 alignment | M-recall 0.459 (M-precision 0.944·M-F1 0.618) | cascade | ✅ M 탐지 유지 (precision 0.944) |
| 9 verdict | exact-match 1.000 | 격리(결정적) | ✅ 산식 정확 (당연한 만점) |

### 분석
병목=4 retrieve→5 fetch RAG 구간. 2c5fa86로 stage7 macro-F1 0.506→0.560·recall[F] 0.583→0.667 상승(단위 NEI 회수). 2 추출 안정(F1 0.959)·유형분류 약함.

### 개선 전후 비교
260622→260623(2c5fa86): 7 macro-F1 0.506→0.560, recall[F] 0.583→0.667. 5·6·8은 LLM 비결정 노이즈 내.

### 한계·주의
cascade는 상류 오류 전파(자체 실력≠표 수치; 8단계 격리 M-recall 0.967). 비율 wilson_ci, n<~30(3·6·9) 참고.
