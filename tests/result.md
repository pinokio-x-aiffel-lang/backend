> ⚠️ 임시 파일 — 테스트 산출물 덤프. 커밋 대상 아님.

# 단계별 기록 (각 단계가 채운 부분)

## 1. 기사 내용 확인

- **article.article_id**: art-0001
- **article.title**: None
- **article.content**: 통계청에 따르면 2024년 합계출산율은 0.72명이다.
- **article.published_at**: None
- **article.source**: None
- **article.url**: None

## 2. 클레임 추출

- **claims[0].claim_id**: clm-0001
- **claims[0].article_id**: art-0001
- **claims[0].sentence**: 통계청에 따르면 2024년 합계출산율은 0.72명이다.
- **claims[0].claim_type**: ClaimType.OTHER
- **claims[0].subject**: 합계출산율
- **claims[0].value.raw**: 0.72
- **claims[0].value.llm_value**: 
- **claims[0].value.is_inferred**: False
- **claims[0].unit**: 명
- **claims[0].aggregation**: 값
- **claims[0].period_type**: Y
- **claims[0].period_value.raw**: 2024년
- **claims[0].period_value.llm_value**: 
- **claims[0].period_value.is_inferred**: False
- **claims[0].compare_period_value**: None
- **claims[0].compare_group**: None
- **claims[0].population**: 전체 인구
- **claims[0].cited_source**: 통계청

## 3. 한국어 수사 산술로 변환

- **claims[0].value.llm_value**:  → 0.72
- **claims[0].period_value.llm_value**:  → 2024

## 4. KOSIS 통계표 찾기

- **analysis[0].claim_id**: clm-0001
- **analysis[0].kosis_search.api**: statisticsSearch.do
- **analysis[0].kosis_search.query**: 합계출산율
- **analysis[0].kosis_search.params**: (더미)
- **analysis[0].kosis_search.hits**: 1
- **analysis[0].kosis_search.selected_tbl_id**: DT_DUMMY
- **analysis[0].kosis_search.selected_tbl_name**: (더미) 인구동향조사
- **analysis[0].kosis_search.success**: 1
- **analysis[0].kosis_search.error_msg**: None
- **analysis[0].kosis_search.duration_ms**: 0
- **analysis[0].kosis_query.api**: statisticsData.do
- **analysis[0].kosis_query.tbl_id**: DT_DUMMY
- **analysis[0].kosis_query.params**: 
- **analysis[0].kosis_query.rows_returned**: 0
- **analysis[0].kosis_query.success**: 0
- **analysis[0].kosis_query.error_msg**: None
- **analysis[0].kosis_query.duration_ms**: 0

## 5. KOSIS 조회

- **analysis[0].kosis_query.params**:  → (더미)
- **analysis[0].kosis_query.rows_returned**: 0 → 1
- **analysis[0].kosis_query.success**: 0 → 1

## 6. 통계 수치 비교 판단

_(변경 없음)_

## 7. 통계수치와 문장의 정합성 판단

_(변경 없음)_

## 8. 종합 분석·검증 결과 생성

- **verifications.summary.total_claims**: 1
- **verifications.summary.overall_verdict**: UNVERIFIED
- **verifications.summary.average_confidence**: 0.0
- **verifications.claim_results[0].claim_id**: clm-0001
- **verifications.claim_results[0].verdict**: UNVERIFIED
- **verifications.claim_results[0].verdict_human**: None
- **verifications.claim_results[0].verdict_human_note**: None
- **verifications.claim_results[0].mismatch_type**: None
- **verifications.claim_results[0].claim_value**: 0.72
- **verifications.claim_results[0].kosis_value**: 0.72
- **verifications.claim_results[0].explanation**: 
- **verifications.claim_results[0].confidence**: 0.0
- **verifications.claim_results[0].llm_model**: (더미)
- **verifications.claim_results[0].evidence[0].claim_id**: clm-0001
- **verifications.claim_results[0].evidence[0].source**: KOSIS
- **verifications.claim_results[0].evidence[0].subject**: 합계출산율
- **verifications.claim_results[0].evidence[0].unit**: 명
- **verifications.claim_results[0].evidence[0].period_type**: Y
- **verifications.claim_results[0].evidence[0].period**: 2024
- **verifications.claim_results[0].evidence[0].population**: 전체 인구
- **verifications.claim_results[0].evidence[0].evidence_id**: None
- **verifications.claim_results[0].evidence[0].value**: None
- **verifications.claim_results[0].evidence[0].kosis_org_id**: None
- **verifications.claim_results[0].evidence[0].kosis_tbl_id**: None
- **verifications.claim_results[0].evidence[0].table_name**: None
- **verifications.claim_results[0].evidence[0].kosis_item_id**: None
- **verifications.claim_results[0].evidence[0].url**: None
- **verifications.claim_results[0].evidence[0].last_updated**: None
- **verifications.claim_results[0].evidence[0].retrieved_at**: None

## 9. 설명 생성

- **verifications.claim_results[0].explanation**:  → 2024년 합계출산율에 대한 KOSIS 공식 통계를 찾지 못해 검증할 수 없습니다.
