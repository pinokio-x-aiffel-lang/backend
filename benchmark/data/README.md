### `1_e2e.txt`
E2E의 전체 파이프라인이 중단없이 도는지 확인하기 위한 테스트 셋으로 평가셋v2(260605)에서 T/F/M-S/NEI 각 10개씩 총 40개로 구성되어 있습니다.

### 2_single_sentence_for_claim_extractor.txt
- source: 0_origin_50set.txt
- 구성: 50개의 양성 + 50개의 음성 문장
    - 양성: claim 추출이 가능한 문장
    - 음성: 통계적 수치처럼 보이지만 claim이 아닌 문장

### 0_origin_50set.txt
- source: 클라비 데이터 중 일부  
조선일보 기사 원문에서 가져온 50개의 원본 문단입니다.

