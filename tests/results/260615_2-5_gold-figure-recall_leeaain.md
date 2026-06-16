# 260615_2-5_gold-figure-recall_leeaain

### 1. 테스트 목적
`from_labeled_true_2~6_source.jsonl`(123건, 전부 label=True)의 각 claim을 파이프라인 [1]~[5]로 흘려보내고, **[5] fetch_kosis_data가 가져온 값이 gold(원래 통계표 수치)를 재현하는지**(gold figure recall)를 채점한다.

### 2. 검증 대상 모듈
- src/modules/fetch_kosis_data.py — [5] KOSIS 셀 값 조회

### 3. 도구로만 쓰인 모듈 (검증 대상 아님)
- [1] load_article · [2] extract_statistical_claims · [3] normalize_claim · [4] retrieve_kosis_candidates (흘려보내기용; subject/population은 [2]가 생성)

### 4. 테스트 일자 / 작성자
- 일자: 2026-06-15
- 작성자: leeaain

### 5. 결과  (원자료: 260615_2-5_gold-figure-recall_leeaain.json)
- 레코드: 123 (성공 123 / 실패 0)
- evidence 1개+ 확보 레코드: 47/123
- 추출 claim 총 240 · evidence 총 166

**gold figure 분류**: 단일값 226 = 절대값형 70 + 증감형(미배선) 156 · 제외(범위/항목없음) 10

- **[5] 절대값 재현율 (값): 0.171** (12/70)  ← 주지표
- [5] 절대값 재현율 (값+시점): 0.086 (6/70)
- (참고) 증감형 gold 적중: 0/156 — 절대조회로는 재현 불가(그룹연산 미배선, 거의 0이 정상)

### 6. 한계 / 범위 밖
- gold tbl_id 없음 → [4] 표 recall은 직접 채점 불가(값 일치로 간접).
- 값 정규화([3] value)·subject/population([2]) 정답 없음 → 본 채점은 [5] 값 한정.
- **증감형 gold**(증감/전년동월비 등)는 [5] 절대조회로 재현 불가 → 별도 집계, 주지표서 제외.
- 범위·비교형 gold(period 'A~B'/다중값)는 단일셀 대조 불가라 제외.
- 발행일 미상 → [1]의 더미 base(2025-04)로 상대시점 정규화(일부 오차 가능).
- 관측: population 미추출 시 [5]가 전국(계) 대신 시도값을 매칭하는 경향(예 id1: 5116≠28589).
- label이 전부 True → 가짜 탐지(7~9)는 범위 밖.