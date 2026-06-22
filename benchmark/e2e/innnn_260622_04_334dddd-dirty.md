# innnn_260622_04_334dddd-dirty — e2e 성능 평가

### 개요
HCX-007 Think + HCX-005 Act, 아인님 2·3·6~10단계 통합 e2e 파이프라인 평가. SSOT 213행 (T123/F30/M30/NEI30). [4+5]: map_claim_via_agent (HCX-007 think:low → HCX-005 FC). Langfuse 트레이싱: row별 root span + 단계 span + KOSIS HTTP span.

### 테스트 방법
SSOT 213행 → 1~10단계 전체 파이프라인. 동시 처리 5행. [5] 허용오차: 절대 1.0 또는 상대 2%(T-label만 채점). [6] Top-1 value-recall = evidences[0].value ≈ gold_figures(proxy). [7] gold 매핑: T→T, F→F, M→M, NEI→N. [2][3] P/R/F1·accuracy: eval_stage2.py / eval_stage3.py 별도 실행 필요.

### 성능 수치
| 지표 | 종류 | 값 | 95% CI |
|---|---|---|---|
| [2] claim 추출 행(1건 이상) | coverage | 0.000 (0/213) | [0.000, 0.018] |
| [4+5] 조회 성공률(coverage) | coverage | 0.000 (0/213) | [0.000, 0.018] |
| [4+5] value-recall (T-label) | accuracy | 0.000 (0/123) | [0.000, 0.030] |
| macro-F1 | macro-f1 | 0.062 | — |
| recall[T] | recall | 0.000 (0/123) | [0.000, 0.030] |
| recall[F] | recall | 0.000 (0/30) | [-0.000, 0.114] |
| recall[M] | recall | 0.000 (0/30) | [-0.000, 0.114] |
| recall[N] | recall | 1.000 (30/30) | [0.886, 1.000] |
| M-recall | recall | 0.000 (0/30) | [-0.000, 0.114] |
| M-precision | precision | — (0/0) | [0.000, 0.000] |
| M-F1 | f1 | 0.000 | — |
| exact-match | exact | 0.141 (30/213) | [0.100, 0.194] |

### 분석
| 관문 | 건수 |
|---|---|
| 입력 row | 213 |
| claim 추출 | 0 |
| evidence 확보(answered) | 0 |
| 오류 발생 claim | 213 |
| 판정 T | 0 |
| 판정 F | 0 |
| 판정 M | 0 |
| 판정 N(NEI) | 213 |

### 개선 전후 비교
_(작성 필요)_

### 한계·주의
[4+5] value-recall은 T-label gold_figures 보유 행만. [6] Top-1은 agent가 반환한 evidences[0] 단일 값 기준(rank 의미 없음). [2][3] cascade 측정이라 상류 오류 섞임. 클래스 불균형(T:123 vs F/M/NEI 각 30) — 신뢰구간 보수 해석.
