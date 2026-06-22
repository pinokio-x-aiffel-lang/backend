# 단계별 성능 통합표 (2~9) — 260623 재실행

### 개요
파이프라인 단계별 성능 통합표(2~9). 고정 SSOT 213기사. 단계별 방법(격리/value-recall/cascade)대로 1차 지표 채점, 260623 재실행.

### 테스트 방법
2 claim=격리 LLM(2_source_1, 양성63/음성37), 4 retrieve=value-recall(SSOT figure↔후보표 KOSIS raw, 226 figure), 9 verdict=격리 결정적(11). 3·5·6·7·8=260622 캡처 슬라이스 vs 독립 gold cascade. 채점=STAGE_SCORERS, 저장=save_result.

### 성능 수치
| 단계 | 1차 지표 | 방법 | 평가 |
|---|---|---|---|
| 2 claim | 문장 F1 0.959 (P 0.983·R 0.937) · claim_type acc 0.551 | 격리(LLM) | ✅ 추출 양호 / ⚠️ 유형분류 약함 |
| 3 normalize | value 1.000 · period 0.238 | cascade | ❌ period 약함 (value n=22 불확실) |
| 4 retrieve | Recall@10 0.350 · @1 0.128 · MRR 0.210 | value-recall | ❌ 정답표 65% 놓침 |
| 5 fetch | coverage 0.493 · 셀값 0.415 | cascade | ❌ 실효 정답셀 ≈ 0.20 |
| 6 rank | Top-1 0.548 | cascade | △ 보통, n=31 작음 |
| 7 metric | macro-F1 0.506 · recall[T] 0.103·F 0.583·N 1.0 | cascade | ⚠️ 0.337→0.506 개선, 상류 cascade 영향 |
| 8 alignment | M-recall 0.486 (M-precision 0.947·M-F1 0.643) | cascade | ✅ 0.000→0.486 회복 |
| 9 verdict | exact-match 1.000 | 격리(결정적) | ✅ 산식 정확 (당연한 만점) |

### 분석
병목=4 retrieve(정답표 65% 놓침)→5 fetch(실효 정답셀 ≈0.20). 7·8은 상류 cascade 오류가 분모에 남아 상한 눌림. 2 claim 추출 안정(F1 0.959)·유형분류 약함(0.551).

### 개선 전후 비교
260619→현행: 7 macro-F1 0.337→0.506, 8 M-recall 0.000→0.486. 상류 2~6 코드 무변(3 normalize 동률). cascade 3·5·6·7·8은 260622와 동일(결정적 재채점); 2·4는 비결정 재실행(노이즈 내).

### 한계·주의
cascade는 gold-isolation 아님 — 상류 오류 전파(자체 실력≠표 수치; 8단계 격리 M-recall 0.967). 비율 wilson_ci, n<~30(3·6·9) 참고. 4 델타형 figure는 단일 셀 부재로 자연 미검출.
