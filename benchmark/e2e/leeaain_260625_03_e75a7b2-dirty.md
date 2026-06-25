# leeaain_260625_03_e75a7b2-dirty — e2e 성능 평가

### 개요
e2e 전체 평가 — funnel·verdict 분포·coverage + 최종 verdict vs 독립 gold.

### 테스트 방법
고정 SSOT 213 → 현재 파이프라인 1~10단계 캡처(260625_capture_v2_premerge_top30_cr.jsonl). funnel/분포/coverage=캡처 집계, 정답대조=after9 vs 독립 gold(7·8 v2 testset).

### 성능 수치
| 지표 | 값 | 95% CI | 비고 |
|---|---|---|---|
| 기사 완주율 | 1.000 (213/213) | [0.982, 1.000] | raise 0 기대 |
| 추출 claim 수 | 395 | — | 213 완주 기사 |
| [4] 검색 hit>0 | 0.995 (393/395) | [0.982, 0.999] | retrieve |
| [5] evidence 확보 | 0.425 (168/395) | [0.378, 0.475] | fetch |
| 판정값 도달(value-reach) | 0.425 (168/395) | [0.378, 0.475] | kosis_value |
| 최종 판정 분포 | T 22 · F 64 · M 18 · N 291 | — | claim(after9) |
| coverage(생존율) | 0.263 (104/395) | [0.222, 0.309] | (T+F+M)/total |
| gap(값 도달−coverage) | 0.162 | — | 값 왔는데 NEI |
| macro-F1 | 0.558 | — | after9 vs gold(T/F/N) |
| recall[T] | 0.205 (8/39) | [0.108, 0.355] | 진짜 T→T |
| recall[F] | 0.556 (20/36) | [0.396, 0.705] | 거짓→F |
| recall[N] | 1.000 (51/51) | [0.930, 1.000] | 불가→N |
| M-recall | 0.459 (17/37) | [0.310, 0.616] | 왜곡 탐지 |
| M-precision | 0.944 (17/18) | [0.742, 0.990] |  |

### 분석
완주 213/213, claim 395, 분포 {'T': 22, 'N': 291, 'F': 64, 'M': 18}, coverage 104/395.

### 개선 전후 비교
_(작성 필요)_

### 한계·주의
최종 verdict 지표는 scorable claim만 분모. cascade라 상류 셀-매칭 오류가 상한을 누름.
