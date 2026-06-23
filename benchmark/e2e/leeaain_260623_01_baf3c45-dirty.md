# e2e 최종 평가 (평가지표별 결과표) — 재실행

### 개요
e2e 최종 평가(재실행) — 파이프라인 코드 무변경이라 고정 260622 캡처(213기사, 실패 0)를 하니스로 재채점. 최종 산출(after9, claim 393건)을 퍼널·분포·coverage·독립 gold 정답대조로 평가. claim 단위(decide_verdict 단일라벨 미산출).

### 테스트 방법
입력=SSOT 213기사 고정. 퍼널/분포/coverage=260622 캡처 직접 집계. 정답대조=최종 verdict(after9) vs 독립 gold(7 gold_verdict_stage7 · 8 is_M · 9 결정적 집계). 비순환 gold. 재실행=결정적(수치 동일).

### 성능 수치
| 지표 | 값 | 95% CI | 비고 |
|---|---|---|---|
| 기사 완주율 | 1.000 (213/213) | [0.982, 1.000] | raise 0 |
| 추출 claim 수 | 393 | — | SSOT 213기사 |
| [4] 검색 hit>0 | 0.997 (392/393) | [0.986, 1.000] | retrieve 후보 확보 |
| [5] evidence 확보 | 0.410 (161/393) | [0.362, 0.459] | fetch 셀 확보 |
| 판정값 도달(value-reach) | 0.410 (161/393) | [0.362, 0.459] | kosis_value 도달 |
| 최종 판정 분포 | T 8·F 71·M 19·N 295 | — | claim 단위 |
| coverage(생존율, non-NEI) | 0.249 (98/393) | [0.209, 0.294] | (T+F+M)/total |
| gap(값왔는데 NEI) | 0.160 | — | value_reach−coverage 손실 |
| 최종 verdict macro-F1 (T/F/N) | 0.496 | — | after9 vs 독립 gold |
| recall[T] (절대 T 재현) | 0.079 (3/38) | [0.027, 0.208] | 진짜 T를 T로 |
| recall[F] | 0.600 (21/35) | [0.436, 0.744] | 거짓을 F로 |
| recall[N] | 1.000 (50/50) | [0.929, 1.000] | 검증불가를 N으로 |
| M-recall | 0.500 (18/36) | [0.345, 0.655] | 오도/왜곡(is_M) 탐지 |
| M-precision | 0.947 (18/19) | [0.754, 0.991] |  |
| 집계 산식 exact-match | 1.000 | — | stage9 결정적(11/11) |

### 분석
coverage(생존율)=0.249: claim 393건 중 98건만 실판정. 퍼널 hit 392→evidence 161→value 161→non-NEI 98. gap 0.160. 병목=4 retrieve+5 fetch. 정답대조 macro-F1 0.496, recall[T] 3/38·F 21/35, M-recall 0.500.

### 개선 전후 비교
260622_04 대비 동일(코드 무변경, 결정적 재채점). 260619 대비: macro-F1 0.337→0.496, M-recall 0.000→0.500.

### 한계·주의
coverage는 cascade(상류 4·5 셀-매칭 오류 분모 잔존). 8단계 격리 M-recall 0.967. 비율 wilson_ci, 소표본(T·M) 참고.
