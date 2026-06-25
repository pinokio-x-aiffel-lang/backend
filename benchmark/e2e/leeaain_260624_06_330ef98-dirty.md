# leeaain_260624_06_330ef98-dirty — e2e 성능 평가

### 개요
e2e 전체 평가 — funnel·verdict 분포·coverage + 최종 verdict vs 독립 gold.

### 테스트 방법
고정 SSOT 213 → 현재 파이프라인 1~10단계 캡처(260624_capture_v2_330ef98.jsonl). funnel/분포/coverage=캡처 집계, 정답대조=after9 vs 독립 gold(7·8 v2 testset).

### 성능 수치
| 지표 | 값 | 95% CI | 비고 |
|---|---|---|---|
| 기사 완주율 | 1.000 (213/213) | [0.982, 1.000] | raise 0 기대 |
| 추출 claim 수 | 401 | — | 213 완주 기사 |
| [4] 검색 hit>0 | 0.903 (362/401) | [0.870, 0.928] | retrieve |
| [5] evidence 확보 | 0.369 (148/401) | [0.323, 0.417] | fetch |
| 판정값 도달(value-reach) | 0.369 (148/401) | [0.323, 0.417] | kosis_value |
| 최종 판정 분포 | T 19 · F 38 · M 11 · N 333 | — | claim(after9) |
| coverage(생존율) | 0.170 (68/401) | [0.136, 0.209] | (T+F+M)/total |
| gap(값 도달−coverage) | 0.200 | — | 값 왔는데 NEI |
| macro-F1 | 0.515 | — | after9 vs gold(T/F/N) |
| recall[T] | 0.256 (10/39) | [0.146, 0.411] | 진짜 T→T |
| recall[F] | 0.333 (12/36) | [0.202, 0.497] | 거짓→F |
| recall[N] | 1.000 (51/51) | [0.930, 1.000] | 불가→N |
| M-recall | 0.270 (10/37) | [0.154, 0.430] | 왜곡 탐지 |
| M-precision | 0.909 (10/11) | [0.623, 0.984] |  |

### 분석
완주 213/213, claim 401, 분포 {'N': 333, 'T': 19, 'M': 11, 'F': 38}, coverage 68/401.

### 개선 전후 비교
_(작성 필요)_

### 한계·주의
최종 verdict 지표는 scorable claim만 분모. cascade라 상류 셀-매칭 오류가 상한을 누름.
