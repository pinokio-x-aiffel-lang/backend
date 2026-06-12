# [10] generate_explanation 종합 의견 테스트 — 2026-06-12

1. **테스트 목적**: [10] generate_explanation 이 생성하는 기사 단위 LLM 종합 의견의 품질 확인
2. **검증 대상 모듈**: `src/modules/generate_explanation.py` (특히 `_generate_opinion`)
3. **도구로만 쓰인 모듈**: `src/llm/*`(LlmCaller·HCX-005), `src/prompts/prompts.py`, `src/schemas/runtime.py`
4. **일자/작성자**: 2026-06-12 / innnn

- 원자료(JSON): `tests/results/260612_10_generate-explanation_innnn.json`
- overall_verdict: **F**

## 기사 단위 종합 의견 (LLM)

> 이 기사는 총 네 가지 통계를 다루고 있으며 그중 두 가지는 정확하고(청년 실업률과 합계 출산율), 하나는 검토가 필요한 상태이며(주당 평균 근로시간) 나머지 하나(노인 빈곤율)는 비교할 데이터 자체가 없어 검증이 불가능합니다. 따라서 이 기사의 전반적인 통계 신뢰성은 부분적으로 타당한 것으로 보입니다. 일부 데이터에서 약간의 차이가 있는 점을 감안하면 독자들은 추가적인 출처 확인을 통해 정보를 교차 검증하는 것이 좋습니다.

## claim별 템플릿 설명

| claim | verdict | explanation |
|---|---|---|
| c1 | F | 기사의 2023년 청년 실업률 6.5%는 KOSIS 공식 수치(7.1%)와 다릅니다. 불일치 유형: magnitude. (출처: 경제활동인구조사) |
| c2 | T | 기사의 2024년 합계출산율 0.72명은 KOSIS 공식 수치와 일치합니다. (출처: 인구동향조사) |
| c3 | M | 기사의 2024년 주당 평균 근로시간 38.8시간은 KOSIS 공식 수치(38.8시간)와 부분적으로 일치합니다. (출처: 근로형태별 근로실태조사) |
| c4 | N | 2023년 노인 빈곤율에 대한 KOSIS 공식 통계를 찾지 못해 검증할 수 없습니다. |
