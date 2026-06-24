# leeaain_260624_02_f4d9ef9-dirty — [7] calculate_metric 성능 평가

### 개요
7단계 calculate_metric **frozen-독립** 평가 — macro-F1 + recall[T/F/N].

### 테스트 방법
격리: 독립 claim_value(7_source_1) + 독립 official figure(5_source_1.gold)를 row_id 조인 → claim+evidence MasterSchema → calculate_metric(결정적) → verdict 를 gold_verdict_stage7 대조. 무증거(N)는 evidence 없이 주입. 캡처 아님.

### 성능 수치
| 지표 | 종류 | 값 | 95% CI |
|---|---|---|---|
| macro-F1 | macro-f1 | 0.858 | — |
| recall[T] | recall | 0.692 (18/26) | [0.500, 0.835] |
| recall[F] | recall | 0.842 (16/19) | [0.624, 0.945] |
| recall[N] | recall | 1.000 (51/51) | [0.930, 1.000] |

### 분석
캡처 입력(stale) 대체: 공식값을 SSOT figure 로 고정해 상류와 무관하게 비교 로직만 측정.

### 개선 전후 비교
_(작성 필요)_

### 한계·주의
official 값이 SSOT figure 로 존재하는 행만(주로 T/F). N 은 무증거로 표현. 단위 환산은 calculate_metric 내부 규칙에 의존.
