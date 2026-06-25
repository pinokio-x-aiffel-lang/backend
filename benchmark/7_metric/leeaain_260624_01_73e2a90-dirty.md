# leeaain_260624_01_73e2a90-dirty — [7] calculate_metric 성능 평가

### 개요
7단계 v2 cascade 평가(현재 파이프라인 캡처 input·독립 gold).

### 테스트 방법
260623_capture_v2_snapshots.jsonl 캡처 슬라이스 vs 독립 gold. 상류=파이프라인 출력(gold-isolation 아님).

### 성능 수치
| 지표 | 종류 | 값 | 95% CI |
|---|---|---|---|
| macro-F1 | macro-f1 | 0.617 | — |
| recall[T] | recall | 0.308 (12/39) | [0.186, 0.464] |
| recall[F] | recall | 0.583 (21/36) | [0.422, 0.729] |
| recall[N] | recall | 1.000 (51/51) | [0.930, 1.000] |

### 분석
검증 목적 채점 — 하니스 계약 통과 + 지표 산출.

### 개선 전후 비교
_(작성 필요)_

### 한계·주의
scorable 행만 분모. cascade 라 상류 오류가 하류로 전파.
