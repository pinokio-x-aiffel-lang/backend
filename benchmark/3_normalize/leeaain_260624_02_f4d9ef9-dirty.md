# leeaain_260624_02_f4d9ef9-dirty — [3] normalize_claim 성능 평가

### 개요
3단계 normalize_claim value·period·compare accuracy + 룰 커버리지.

### 테스트 방법
모듈 격리: 3_source(n=507) raw+base 고정 주입, _normalize_one 실행, 독립 gold(expected)와 대조.

### 성능 수치
| 지표 | 종류 | 값 | 95% CI |
|---|---|---|---|
| value accuracy | accuracy | 0.992 (121/122) | [0.955, 0.999] |
| period accuracy | accuracy | 0.755 (74/98) | [0.661, 0.830] |
| compare_period accuracy | accuracy | 0.543 (44/81) | [0.435, 0.647] |
| 룰 커버리지 | coverage | 0.980 (497/507) | [0.964, 0.989] |

### 분석
값 오탐 가드(비수치어→허수) 수정 반영 측정.

### 개선 전후 비교
_(작성 필요)_

### 한계·주의
gold expected 있는 슬롯만 분모. 일부 period 는 LLM 폴백 포함.
