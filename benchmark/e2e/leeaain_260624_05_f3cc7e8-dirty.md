# leeaain_260624_05_f3cc7e8-dirty — e2e 성능 평가

### 개요
e2e 전체 평가 — funnel·verdict 분포·coverage + 최종 verdict vs 독립 gold.

### 테스트 방법
고정 SSOT 213 → 현재 파이프라인 1~10단계 캡처(260624_capture_v2_fixed.jsonl). funnel/분포/coverage=캡처 집계, 정답대조=after9 vs 독립 gold(7·8 v2 testset).

### 성능 수치
| 지표 | 값 | 95% CI | 비고 |
|---|---|---|---|
| 기사 완주율 | 1.000 (213/213) | [0.982, 1.000] | raise 0 기대 |
| 추출 claim 수 | 441 | — | 213 완주 기사 |
| [4] 검색 hit>0 | 0.900 (397/441) | [0.869, 0.925] | retrieve |
| [5] evidence 확보 | 0.417 (184/441) | [0.372, 0.464] | fetch |
| 판정값 도달(value-reach) | 0.408 (180/441) | [0.363, 0.455] | kosis_value |
| 최종 판정 분포 | T 0 · F 41 · M 0 · N 400 | — | claim(after9) |
| coverage(생존율) | 0.093 (41/441) | [0.069, 0.124] | (T+F+M)/total |
| gap(값 도달−coverage) | 0.315 | — | 값 왔는데 NEI |
| macro-F1 | 0.391 | — | after9 vs gold(T/F/N) |
| recall[T] | 0.000 (0/39) | [0.000, 0.090] | 진짜 T→T |
| recall[F] | 0.389 (14/36) | [0.248, 0.551] | 거짓→F |
| recall[N] | 1.000 (51/51) | [0.930, 1.000] | 불가→N |
| M-recall | 0.000 (0/37) | [0.000, 0.094] | 왜곡 탐지 |
| M-precision | — (0/0) | [0.000, 0.000] |  |

### 분석
완주 213/213, claim 441, 분포 {'N': 400, 'F': 41}, coverage 41/441.

### 개선 전후 비교
_(작성 필요)_

### 한계·주의
최종 verdict 지표는 scorable claim만 분모. cascade라 상류 셀-매칭 오류가 상한을 누름.
