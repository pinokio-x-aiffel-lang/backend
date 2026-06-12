# [10] generate_explanation 종합 의견 테스트 — 2026-06-12

1. **테스트 목적**: [10] generate_explanation 이 생성하는 기사 단위 LLM 종합 의견의 품질 확인
2. **검증 대상 모듈**: `src/modules/generate_explanation.py` (특히 `_generate_opinion`)
3. **도구로만 쓰인 모듈**: `src/llm/*`(LlmCaller·HCX-005), `src/prompts/prompts.py`, `src/schemas/runtime.py`
4. **일자/작성자**: 2026-06-12 / innnn

- 원자료(JSON): `tests/results/260612_10_generate-explanation_innnn_01.json`
- verdict_counts: **{'T': 1, 'F': 1, 'M': 1, 'N': 1}** / 사실 비율(overall_confidence): **33%**

## 기사 단위 종합 의견 (LLM)

> 이 기사는 총 네 가지 통계 주장을 다루고 있으며, 그중 세 가지는 부분적으로 정확하거나 오해를 일으킬 가능성이 있습니다. 두 개의 수치(청년 실업률 및 주당 평균 근로시간)에서 기사와 공식 통계 간의 차이가 존재하며, 나머지 하나(합계출산율)는 정확히 일치합니다. 또한 노인 빈곤율에 관한 공식 통계가 없기 때문에 이 부분은 검증할 수 없습니다. 따라서 전체적으로 볼 때, 이 기사의 통계 인용은 일부 부정확성과 모호한 부분이 있어 주의 깊게 읽어야 할 필요가 있습니다.

## claim별 템플릿 설명

| claim | verdict | explanation |
|---|---|---|
| c1 | F | 기사의 2023년 청년 실업률 6.5%는 KOSIS 공식 수치(7.1%)와 다릅니다. 불일치 유형: magnitude. (출처: 경제활동인구조사) |
| c2 | T | 기사의 2024년 합계출산율 0.72명은 KOSIS 공식 수치와 일치합니다. (출처: 인구동향조사) |
| c3 | M | 기사의 2024년 주당 평균 근로시간 38.8시간은 KOSIS 공식 수치(38.8시간)와 부분적으로 일치합니다. (출처: 근로형태별 근로실태조사) |
| c4 | N | 2023년 노인 빈곤율에 대한 KOSIS 공식 통계를 찾지 못해 검증할 수 없습니다. |
