# leeaain_260623_03_8b9c397-dirty — [4] retrieve_kosis_candidates 성능 평가

### 개요
4단계 **값-기반 Recall** — 파이프라인이 검색한 후보표(candidates) 중 하나라도 figure 값을 실제로 담고 있는지 KOSIS raw로 확인. 정답 '표' 라벨링 없이 figure 값(SSOT, 독립)만으로 측정.

### 테스트 방법
T 226개 figure 대상. 각 figure의 값을 후보표들에서 raw call_kosis로 순위대로 조회 → 값이 처음 든 후보 순위=gold_rank → Recall@N/MRR. 비순환(값=독립, 후보=캡처, 확인=raw KOSIS).

**데이터 출처 (골든셋 ≠ 입력, 서로 다른 파일)**
- 골든셋(정답): `benchmark/data/ssot/260614_master_eval_213_parsed_human_checked_SSOT.jsonl` 의 `gold_figures` — T행 figure 값(사람검수·독립). 채점 기준.
- 입력(채점 대상): `benchmark/data/4_retrieve/4_source_1.jsonl` 의 `candidates` — 파이프라인이 검색한 후보 표 풀(캡처). `gold_tbl_id` 칸은 비움(표-라벨링 대신 값-기반 채점).
- 채점 질문: 입력(후보 풀)이 골든셋 figure 값을 담고 있나 → gold_rank.

### 성능 수치
| 지표 | 종류 | 값 | 95% CI |
|---|---|---|---|
| Recall@1 | recall | 0.128 (29/226) | [0.091, 0.178] |
| Recall@3 | recall | 0.279 (63/226) | [0.224, 0.341] |
| Recall@10 | recall | 0.350 (79/226) | [0.290, 0.414] |
| MRR | mrr | 0.210 | — |
| 검색 실패율 | fail-rate | 0.013 (3/226) | [0.005, 0.038] |

### 분석
**Recall@N 읽는 법**: @ 뒤 숫자 = 상위 몇 개 후보까지 보는가. @1=정답이 1순위 / @3=상위 3개 안 / @10=상위 10개 안 비율. 넓게 볼수록(N↑) 값 상승, 만점 1.0. 한 번의 테스트를 세 깊이에서 본 것.

값-기반 Recall은 '검색이 값이 든 표를 가져왔나'를 본다(정본명 일치보다 시스템 목적에 부합). 표 라벨링이 필요 없어 **전 T행 채점 가능**. 델타(증감) figure는 값이 셀에 없어 자연히 미검출 → 정직한 결과.

### 개선 전후 비교
표-기반 recall(leeaain_260619_01)과 비교: 표 유일성 제약을 없애 과소평가를 줄임.

### 한계·주의
① 후보(candidates)는 2026-06-14 캡처. ② 델타 figure는 단일 셀에 없어 미검출(검색 탓 아님). ③ 값-일치는 셀이 그 값을 담는다는 의미일 뿐, 항목/축 정합성은 별도(stage5).
