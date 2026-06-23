# leeaain_260623_07_6b6650e-dirty — [8] check_alignment 성능 평가

### 개요
8단계 check_alignment **격리** 평가 — verdict=T+올바른 증거+왜곡문장 주입해 M-recall/precision 실측.

### 테스트 방법
격리: 8_source_3(원천소스 추출)의 claim·evidence로 MasterSchema 구성, metric.verdict=T 주입 → check_alignment 실행 → 재판정 verdict==M=pred_M. gold_M=label==M(병인님 왜곡). cascade(M-recall 0.0)와 달리 모듈 실제 실행.

### 성능 수치
| 지표 | 종류 | 값 | 95% CI |
|---|---|---|---|
| M-recall | recall | 0.967 (29/30) | [0.833, 0.994] |
| M-precision | precision | 0.879 (29/33) | [0.727, 0.952] |
| M-F1 | f1 | 0.921 | — |
| NEI(LLM 실패)율 | nei-rate | 0.000 (0/153) | [0.000, 0.024] |

### 분석
이 수치가 8단계 프롬프트의 진짜 왜곡탐지 실력. M-recall=왜곡을 M으로 잡은 비율, M-precision=M판정 중 진짜 M.

### 개선 전후 비교
cascade(M-recall 0.0, 미실행) → 격리(실측). 0.0은 '상류 막힘'이지 모듈 실력 아니었음을 보임.

### 한계·주의
claim 슬롯(subject/unit/pop)은 병인님·원문 규칙파싱(근사). NEI=LLM 판정실패. 격리는 '올바른 입력 가정' 실력이며, 실운영은 상류가 T를 만들어줘야 발동.
