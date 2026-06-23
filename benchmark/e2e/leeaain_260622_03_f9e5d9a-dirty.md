# e2e 단계별 성능 통합표 (2~9) — 260622 현행

### 개요
파이프라인 e2e 단계별 성능 통합표(2~9단계). 입력=SSOT 213행 고정. 단계별로 정해진 방법(격리/value-recall/cascade)으로 채점한 1차 지표를 한 표로 모음. 260619 스냅샷 대비 현행(커밋 f9e5d9a) 재측정.

### 테스트 방법
전체 파이프라인을 현재 코드로 213행 재캡처(benchmark_aain/data/260622_capture_v2_snapshots.jsonl, 실패 0). 2 claim=격리 LLM(2_source_1, 양성63/음성37), 4 retrieve=value-recall(SSOT figure↔후보표 KOSIS raw, 226 figure), 9 verdict=격리 결정적(11 시나리오). 3·5·6·7·8=캡처 슬라이스 vs 독립 gold cascade 채점. 채점=benchmark/scoring.py STAGE_SCORERS, 저장=reporting.save_result.

### 성능 수치
| 단계 | 1차 지표 | 방법 | 평가 |
|---|---|---|---|
| 2 claim | 문장 F1 0.951 (P 0.983·R 0.921) · claim_type acc 0.531 | 격리(LLM) | ✅ 추출 양호 / ⚠️ 유형분류 약함 |
| 3 normalize | value 1.000 · period 0.238 | cascade | ❌ period 약함 (value n=22 불확실) |
| 4 retrieve | Recall@10 0.350 · @1 0.128 · MRR 0.210 | value-recall | ❌ 정답표 65% 놓침 |
| 5 fetch | coverage 0.493 · 셀값 0.415 | cascade | ❌ 실효 정답셀 ≈ 0.20 |
| 6 rank | Top-1 0.548 | cascade | △ 보통, n=31 작음 |
| 7 metric | macro-F1 0.506 · recall[T] 0.103·F 0.583·N 1.0 | cascade | ⚠️ 0.337→0.506 개선, 상류 cascade 영향 잔존 |
| 8 alignment | M-recall 0.486 (M-precision 0.947·M-F1 0.643) | cascade | ✅ 0.000→0.486 회복 (T입력 생성·framing 탐지) |
| 9 verdict | exact-match 1.000 | 격리(결정적) | ✅ 산식 정확 (당연한 만점) |

### 분석
병목은 4 retrieve(정답표 65% 놓침)→5 fetch(실효 정답셀 ≈0.20)의 RAG 구간. 7·8은 상류 cascade 오류가 분모에 남아 상한이 눌리지만 코드 수정으로 회복: stage7 macro-F1 0.337→0.506, stage8 M-recall 0.000→0.486. 2 claim 추출은 안정(F1 0.951)이나 claim_type 분류는 약함(0.531).

### 개선 전후 비교
260619(이미지) → 260622(현행): 7 macro-F1 0.337→0.506, recall[T] 0.026→0.103·F 0.222→0.583; 8 M-recall 0.000→0.486·M-F1 0.000→0.643. 상류 2~6은 코드 무변(stage3 normalize는 동률). 원인=ef98412(7/8 F·M 탐지)+ae6bb9d(compare_period 기준 시점)+f9e5d9a(compare 추출).

### 한계·주의
cascade(3·5·6·7·8)는 gold-isolation 아님 — 상류 오류가 하류 지표에 전파(자체 실력 ≠ 표 수치). 8단계 격리 M-recall은 0.967(8_alignment 단독). 비율 지표는 wilson_ci, n<~30(3·6·9)은 참고치. 4 retrieve의 델타형 figure는 단일 셀 부재로 자연 미검출(검색 탓 아님).
