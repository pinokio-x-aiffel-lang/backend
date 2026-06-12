# [10] generate_explanation 종합 의견 테스트 — 2026-06-12

1. **테스트 목적**: [10] generate_explanation 이 생성하는 기사 단위 LLM 종합 의견의 품질 확인
2. **검증 대상 모듈**: `src/modules/generate_explanation.py` (특히 `_generate_opinion`)
3. **도구로만 쓰인 모듈**: `src/llm/*`(LlmCaller·HCX-005), `src/prompts/prompts.py`, `src/schemas/runtime.py`
4. **일자/작성자**: 2026-06-12 / innnn

- 원자료(JSON): `tests/results/260612_10_generate-explanation_innnn_02.json`
- verdict_counts: **{'T': 1, 'F': 1, 'M': 1, 'N': 1}** / 사실 비율(overall_confidence): **33%**

## 기사 단위 종합 의견 (LLM)

> 본 기사는 일부 통계에서 정확한 정보를 제공했으나 다른 부분에서는 오류나 모호한 표현으로 인해 독자를 오도할 가능성이 있습니다. 예를 들어, 2023년 청년 실업률은 실제보다 낮게 보도되었고, 주당 평균 근로시간은 동일한 수치임에도 모집단의 차이에 대해 명확히 설명되지 않았습니다. 또한, 2023년 노인 빈곤율은 공식적인 데이터가 없어 그 정확성을 확인할 수 없습니다. 따라서 이 기사의 전반적인 통계 인용 신뢰성은 보통 이하이며, 일부 정보는 주의 깊게 확인해야 할 필요가 있습니다.

## claim별 템플릿 설명

| claim | verdict | explanation |
|---|---|---|
| c1 | F | 기사의 2023년 청년 실업률 6.5%는 KOSIS 공식 수치(7.1%)와 다릅니다. 불일치 유형: magnitude. (출처: 경제활동인구조사) |
| c2 | T | 기사의 2024년 합계출산율 0.72명은 KOSIS 공식 수치와 일치합니다. (출처: 인구동향조사) |
| c3 | M | 기사의 2024년 주당 평균 근로시간 38.8시간은 KOSIS 공식 수치(38.8시간)와 부분적으로 일치합니다. (출처: 근로형태별 근로실태조사) |
| c4 | N | 2023년 노인 빈곤율에 대한 KOSIS 공식 통계를 찾지 못해 검증할 수 없습니다. |
