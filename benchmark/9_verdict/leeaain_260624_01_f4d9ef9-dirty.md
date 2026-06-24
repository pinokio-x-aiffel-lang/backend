# leeaain_260624_01_f4d9ef9-dirty — [9] decide_verdict 성능 평가

### 개요
9단계 decide_verdict — 집계 산식(verdict_counts·overall_confidence=T/(T+F+M)·coverage=(T+F+M)/total) 검증.

### 테스트 방법
모듈 격리: 시나리오별 claim_results(고정 입력)→decide_verdict 실행→summary 산출, 독립 기대 산식과 exact-match. 데이터=benchmark/data/9_verdict/9_source_1.jsonl(11 시나리오).

### 성능 수치
| 지표 | 종류 | 값 | 95% CI |
|---|---|---|---|
| exact-match | exact | 1.000 (11/11) | [0.741, 1.000] |

### 분석
결정적 집계라 오차 0 기대. 불일치 시 산식 회귀(버그).

### 개선 전후 비교
_(작성 필요)_

### 한계·주의
시나리오 11개(합성, 집계 검증용). 실데이터 분포가 아니라 산식 정확성 테스트.
