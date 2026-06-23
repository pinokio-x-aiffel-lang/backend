# leeaain_260623_01_baf3c45-dirty — [2] extract_statistical_claims 성능 평가

### 개요
2단계 extract_statistical_claims — 문장 P/R/F1 + claim_type accuracy. 양성50(수치주장)+음성50(hard-negative).

### 테스트 방법
모듈 격리: 평가셋 문장(사람 라벨)을 Article.content 로 추출 실행. pred_claim=통계 claim(type≠NONE) 추출 여부, gold_claim=label(양성). claim_type=양성·추출성공 행만 ctype_gold↔ctype_pred. 데이터=2_source_1.jsonl(gold 100행).

### 성능 수치
| 지표 | 종류 | 값 | 95% CI |
|---|---|---|---|
| 문장 Precision | precision | 0.983 (59/60) | [0.911, 0.997] |
| 문장 Recall | recall | 0.937 (59/63) | [0.848, 0.975] |
| 문장 F1 | f1 | 0.959 | — |
| claim_type accuracy | accuracy | 0.551 (27/49) | [0.413, 0.681] |
| claim_type macro-F1 | macro-f1 | 0.250 | — |

### 분석
Precision 은 hard-negative 보수치(음성50이 어려운 비-claim).

### 개선 전후 비교
_(작성 필요)_

### 한계·주의
음성=hard-negative만이라 Precision 보수적. claim_type 은 양성 추출성공 분모.
