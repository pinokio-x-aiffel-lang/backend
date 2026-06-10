# 260610_4-10_pipeline-flow_leeaain

### 1. 테스트 목적
claim 5건으로 [4]통계표조회→[5]메타·값→[7]비교→[8]정합성→[9]판정→[10]설명 전 단계가 엮여 동작하는지(실제 값 기반 verdict·설명 생성) 검증.
### 2. 검증 대상 모듈
- src/modules/ [4]retrieve_kosis_candidates [5]fetch_kosis_data [6]rank_evidence [7]calculate_metric [8]check_alignment [9]decide_verdict [10]generate_explanation
### 3. 도구로만 쓰인 모듈 (검증대상 아님)
- src/schemas/runtime.py — Claim/MasterSchema 입력 구성
### 4. 일자 / 작성자
- 2026-06-10 / leeaain

### 5. 결과 (overall=F) · 원자료: 260610_4-10_pipeline-flow_leeaain.json

| claim | 주장값 | KOSIS값 | 비교후보 | verdict | 정합(8) | 설명 |
|---|---|---|---|---|---|---|
| 경제성장률/대한민국 | 1.5 | 1.6 | 2 | F | - | 기사의 2023년 경제성장률 1.5%는 KOSIS 공식 수치(1.6%)와 다릅니다. 불일치 유형: magnitude. (출처: 경제성장률(시도)) |
