# leeaain_260625_07_e75a7b2-dirty — e2e 성능 평가

### 개요
e2e 전체 평가 — funnel·verdict 분포·coverage + 최종 verdict vs 독립 gold.

### 테스트 방법
고정 SSOT 213 → 현재 파이프라인 1~10단계 캡처(260625_capture_v2_norm.jsonl). funnel/분포/coverage=캡처 집계, 정답대조=after9 vs 독립 gold(7·8 v2 testset).

### 성능 수치
| 지표 | 값 | 95% CI | 비고 |
|---|---|---|---|
| 기사 완주율 | 1.000 (213/213) | [0.982, 1.000] | raise 0 기대 |
| 추출 claim 수 | 404 | — | 213 완주 기사 |
| [4] 검색 hit>0 | 0.995 (402/404) | [0.982, 0.999] | retrieve |
| [5] evidence 확보 | 0.465 (188/404) | [0.417, 0.514] | fetch |
| 판정값 도달(value-reach) | 0.463 (187/404) | [0.415, 0.512] | kosis_value |
| 최종 판정 분포 | T 34 · F 62 · M 23 · N 285 | — | claim(after9) |
| coverage(생존율) | 0.295 (119/404) | [0.252, 0.341] | (T+F+M)/total |
| gap(값 도달−coverage) | 0.168 | — | 값 왔는데 NEI |
| macro-F1 | 0.652 | — | after9 vs gold(T/F/N) |
| recall[T] | 0.410 (16/39) | [0.271, 0.566] | 진짜 T→T |
| recall[F] | 0.528 (19/36) | [0.370, 0.680] | 거짓→F |
| recall[N] | 1.000 (51/51) | [0.930, 1.000] | 불가→N |
| M-recall | 0.595 (22/37) | [0.435, 0.737] | 왜곡 탐지 |
| M-precision | 0.957 (22/23) | [0.790, 0.992] |  |

### 분석
완주 213/213, claim 404, 분포 {'T': 34, 'N': 285, 'M': 23, 'F': 62}, coverage 119/404.

### 개선 전후 비교
_(작성 필요)_

### 한계·주의
최종 verdict 지표는 scorable claim만 분모. cascade라 상류 셀-매칭 오류가 상한을 누름.
