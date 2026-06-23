# leeaain_260623_05_8b9c397-dirty — [8] check_alignment 성능 평가

### 개요
8단계 v2 cascade 평가(현재 파이프라인 캡처 input·독립 gold).

### 테스트 방법
260623_capture_v2_run2.jsonl 캡처 슬라이스 vs 독립 gold. 상류=파이프라인 출력(gold-isolation 아님).

### 성능 수치
| 지표 | 종류 | 값 | 95% CI |
|---|---|---|---|
| M-recall | recall | 0.432 (16/37) | [0.287, 0.591] |
| M-precision | precision | 0.941 (16/17) | [0.730, 0.990] |
| M-F1 | f1 | 0.593 | — |

### 분석
검증 목적 채점 — 하니스 계약 통과 + 지표 산출.

### 개선 전후 비교
_(작성 필요)_

### 한계·주의
scorable 행만 분모. cascade 라 상류 오류가 하류로 전파.
