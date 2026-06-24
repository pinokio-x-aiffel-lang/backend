# leeaain_260624_03_f4d9ef9-dirty — [5] fetch_kosis_data 성능 평가

### 개요
5단계 fetch_kosis_data **frozen-독립** 평가 — coverage × 셀값 accuracy(조회분).

### 테스트 방법
격리: 5_source_1(고정 claim+후보 표) → fetch_kosis_data(라이브 KOSIS) → 가져온 셀값이 독립 gold(SSOT figure)와 일치(rel 1%, 천명↔명 ×1000 허용)하나 채점. frozen=입력 고정(캡처 아님), 모듈은 외부 KOSIS 호출.

### 성능 수치
| 지표 | 종류 | 값 | 95% CI |
|---|---|---|---|
| 조회 성공률(coverage) | coverage | 0.422 (79/187) | [0.354, 0.494] |
| 셀값 accuracy(조회분) | accuracy | 0.354 (28/79) | [0.258, 0.464] |

### 분석
coverage=후보표에서 셀 조회 성공률, 셀값 accuracy=조회분 중 figure 일치율. 둘의 곱이 실효 정답셀.

### 개선 전후 비교
_(작성 필요)_

### 한계·주의
입력 후보표는 고정셋(retrieve 품질 미포함 — 그건 4단계). gold=figure 존재 행만. 단위차는 ×1000 근사 허용이라 드문 동일배수 오탐 가능.
