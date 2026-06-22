# leeaain_260622_01_ddab1c1-dirty — e2e 성능 평가

### 개요
8단계(check_alignment) 개선 전후 e2e A/B — after6 동결 입력에 7→8→9 재실행.

### 테스트 방법
BEFORE=260619 캡처 after7/after9 verdict(개선 전). AFTER=같은 after6 입력에 현재 코드 재실행. 동일 v2 gold·scorer·scorable 분모, pred만 교체.

### 성능 수치
| 단계 | 지표 | 방법 | before | after |
|---|---|---|---|---|
| 7 metric | macro-F1 | cascade(재실행) | 0.337 | 0.424 |
| 7 metric | recall[T] | cascade(재실행) | 0.026 (1/39) | 0.051 (2/39) |
| 7 metric | recall[F] | cascade(재실행) | 0.222 (8/36) | 0.389 (14/36) |
| 7 metric | recall[N] | cascade(재실행) | 1.000 (51/51) | 1.000 (51/51) |
| 8 alignment | M-recall | cascade(재실행) | 0.000 (0/37) | 0.351 (13/37) |
| 8 alignment | M-precision | cascade(재실행) | — (0/0) | 0.929 (13/14) |
| 8 alignment | M-F1 | cascade(재실행) | 0.000 | 0.510 |
| 8 alignment | NEI(LLM 실패)율 | cascade(재실행) | — | — |

### 분석
M행 최종 verdict 분포(after)는 print 참조. compare.py 빈단위→가정비교 + 8단계 framing 탐지 프롬프트로 M-recall 0.000 (0/37) → 0.351 (13/37).

### 개선 전후 비교
stage7 macro-F1 0.337→0.424; stage8 M-recall 0.000 (0/37)→0.351 (13/37), M-F1 0.000→0.510. 상류 2~6은 동결(불변).

### 한계·주의
cascade: 상류 5단계 셀-매칭 오류가 그대로 분모에 남아 M-recall 상한을 누른다. 모듈 자체 실력은 격리평가(8_alignment, M-recall 0.967) 참조.
