# innnn_260622_06_334dddd-dirty — e2e 성능 평가

### 개요
아인님 logical 파이프라인 e2e 평가 (retrieve_kosis_candidates + fetch_kosis_data). SSOT 213행 (T123/F30/M30/NEI30). agent 파이프라인(innnn_260622_05)과 직접 비교용.

### 테스트 방법
SSOT 213행 → 1~10단계 전체 파이프라인 (4=retrieve, 5=fetch). 동시 처리 5행. [5] 허용오차: 절대 1.0 또는 상대 2%(T-label만 채점). 비교: innnn_260622_05 (agent) vs 이 결과 (logical).

### 성능 수치
| 지표 | 종류 | 값 | 95% CI |
|---|---|---|---|
| [2] claim 추출 행(1건 이상) | coverage | 1.000 (213/213) | [0.982, 1.000] |
| [4+5] 조회 성공률(coverage) | coverage | 0.174 (78/447) | [0.142, 0.212] |
| [4+5] value-recall (T-label) | accuracy | 0.049 (13/266) | [0.029, 0.082] |
| [6] Top-1 value-recall (proxy) | accuracy | 0.049 (13/266) | [0.029, 0.082] |
| macro-F1 | macro-f1 | 0.097 | — |
| recall[T] | recall | 0.000 (0/266) | [-0.000, 0.014] |
| recall[F] | recall | 0.103 (7/68) | [0.051, 0.198] |
| recall[M] | recall | 0.000 (0/59) | [0.000, 0.061] |
| recall[N] | recall | 1.000 (54/54) | [0.934, 1.000] |
| M-recall | recall | 0.000 (0/59) | [0.000, 0.061] |
| M-precision | precision | — (0/0) | [0.000, 0.000] |
| M-F1 | f1 | 0.000 | — |
| exact-match | exact | 0.136 (61/447) | [0.108, 0.171] |

### 분석
| 관문 | 건수 |
|---|---|
| 입력 row | 213 |
| claim 추출 | 447 |
| evidence 확보(answered) | 78 |
| 오류 발생 claim | 333 |
| 판정 T | 0 |
| 판정 F | 16 |
| 판정 M | 0 |
| 판정 N(NEI) | 431 |

### 개선 전후 비교
agent vs logical 비교 — 성능 수치 표 참조.

### 한계·주의
[4+5] value-recall은 T-label gold_figures 보유 행만. 클래스 불균형(T:123 vs F/M/NEI 각 30) — 신뢰구간 보수 해석.
