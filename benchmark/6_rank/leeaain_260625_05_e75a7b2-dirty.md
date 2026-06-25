# leeaain_260625_05_e75a7b2-dirty — [6] rank_evidence 성능 평가

### 개요
6단계 v2 cascade 평가(현재 파이프라인 캡처 input·독립 gold).

### 테스트 방법
260625_capture_v2_b_basenoun.jsonl 캡처 슬라이스 vs 독립 gold. 상류=파이프라인 출력(gold-isolation 아님).

### 성능 수치
| 지표 | 종류 | 값 | 95% CI |
|---|---|---|---|
| Top-1 accuracy | accuracy | 0.452 (14/31) | [0.292, 0.622] |
| 기권율 | abstain-rate | 0.065 (2/31) | [0.018, 0.207] |

### 분석
검증 목적 채점 — 하니스 계약 통과 + 지표 산출.

### 개선 전후 비교
_(작성 필요)_

### 한계·주의
scorable 행만 분모. cascade 라 상류 오류가 하류로 전파.
