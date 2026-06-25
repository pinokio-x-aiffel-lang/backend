# leeaain_260625_01_e75a7b2-dirty — e2e 성능 평가

### 개요
e2e 전체 평가 — funnel·verdict 분포·coverage + 최종 verdict vs 독립 gold.

### 테스트 방법
고정 SSOT 213 → 현재 파이프라인 1~10단계 캡처(260625_capture_v2_rev4_e75a7b2.jsonl). funnel/분포/coverage=캡처 집계, 정답대조=after9 vs 독립 gold(7·8 v2 testset).

### 성능 수치
| 지표 | 값 | 95% CI | 비고 |
|---|---|---|---|
| 기사 완주율 | 1.000 (213/213) | [0.982, 1.000] | raise 0 기대 |
| 추출 claim 수 | 397 | — | 213 완주 기사 |
| [4] 검색 hit>0 | 0.992 (394/397) | [0.978, 0.997] | retrieve |
| [5] evidence 확보 | 0.529 (210/397) | [0.480, 0.578] | fetch |
| 판정값 도달(value-reach) | 0.526 (209/397) | [0.477, 0.575] | kosis_value |
| 최종 판정 분포 | T 24 · F 53 · M 13 · N 307 | — | claim(after9) |
| coverage(생존율) | 0.227 (90/397) | [0.188, 0.270] | (T+F+M)/total |
| gap(값 도달−coverage) | 0.300 | — | 값 왔는데 NEI |
| macro-F1 | 0.553 | — | after9 vs gold(T/F/N) |
| recall[T] | 0.256 (10/39) | [0.146, 0.411] | 진짜 T→T |
| recall[F] | 0.444 (16/36) | [0.295, 0.604] | 거짓→F |
| recall[N] | 1.000 (51/51) | [0.930, 1.000] | 불가→N |
| M-recall | 0.324 (12/37) | [0.196, 0.485] | 왜곡 탐지 |
| M-precision | 0.923 (12/13) | [0.667, 0.986] |  |

### 분석
완주 213/213, claim 397, 분포 {'T': 24, 'N': 307, 'F': 53, 'M': 13}, coverage 90/397.

### 개선 전후 비교
_(작성 필요)_

### 한계·주의
최종 verdict 지표는 scorable claim만 분모. cascade라 상류 셀-매칭 오류가 상한을 누름.
