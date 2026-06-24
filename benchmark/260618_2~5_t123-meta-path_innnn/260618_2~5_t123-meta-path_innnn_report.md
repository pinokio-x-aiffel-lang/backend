# 260618 · [2+3+4+5] map_claim_via_meta T123 eval · innnn

## 1. Overview

SSOT(`data/260614_master_eval_213_parsed_human_checked_SSOT.jsonl`)에서 `label=T` 123건을 대상으로,
`[2] extract_statistical_claims → [3] normalize_claim → map_claim_via_meta([4+5] 대안 경로)`
전체 파이프라인을 실행해 기준 성능을 측정한다.

Langfuse 트레이싱: 각 문장을 `t123:{row_id}` 루트 span 으로 기록.
채점: `ev` 값 중 하나가 gold_figure 스칼라 값과 ±0.5% 이내로 일치하면 HIT.

## 2. What was tested

| 항목 | 내용 |
|---|---|
| 대상 | SSOT label=T 123건 (취업·실업·물가·인구·소매 등 다양) |
| 파이프라인 | extract → normalize → map_claim_via_meta (load_article 제외, text 직접 주입) |
| gold 기준 | `gold_figures[].value` (병인님 라벨링, KOSIS 실측값) |
| 채점 기준 | sentence_hit(문장 단위 ≥1 일치), gold_recall(스칼라 gold 건수 단위) |
| 허용 오차 | max(0.1, \|gold\| × 0.5%) |
| 제외 | list형 gold(8건), None gold(2건) → scalar gold 226건 채점 |

## 3. 결과

### 3-1. 집계

| 지표 | 결과 |
|---|---|
| **sentence_hit** | **22 / 123 = 17.9%** |
| **gold_recall** | **27 / 226 = 11.9%** |
| errors | 0 |

HIT 행: 1, 9, 15, 16, 21, 22, 23, 32, 37, 41, 46, 49, 52, 64, 72, 81, 83, 95, 105, 106, 114, 118

### 3-2. 실패 유형 분류

| 유형 | 건수 | 설명 |
|---|---|---|
| **ev=[]** (조회 실패) | 52건 | map_claim_via_meta가 KOSIS 셀 자체를 못 찾음 |
| **ev≠gold** (값 불일치) | 49건 | 값은 반환했으나 gold와 불일치 |
| HIT | 22건 | 정상 매칭 |

### 3-3. 실패 패턴 분석

**① 단위/스케일 불일치 (ev≠gold의 주요 원인)**

| row | ev | gold | 추정 원인 |
|---|---|---|---|
| 6 | 918.1, 839.5 | 300, 289 | 천명 vs 만명 단위 혼용 |
| 13 | 2330.1 | 464, 461 | 전체 취업자를 조회, 세부 항목 필요 |
| 14 | 51,751,065 | 52,000 | 명 단위 vs 천명 단위 |
| 18 | -2.02 | -84 | 변화율(%) vs 변화량(천명) |
| 26 | -0.28 | 4,414 | wrong claim type(절대값 vs 변화율) |

**② wrong item — 변화율 claim에서 절대지수 조회**

| row | ev | gold | 추정 원인 |
|---|---|---|---|
| 2 | 0.593 | 32, 129 | 고용률(소수) 조회, 취업자 증감 필요 |
| 7 | 3.8 | 7.5 | 실업률 외 항목 선택 |
| 39 | 114.65, 116.52 | 1.6 | 물가지수 조회, YoY % 필요 |
| 96 | 115.71, 116.08, 116.29 | 2.2, 2.0, 2.1 | 지수 조회했으나 YoY 미계산 |

**③ ev=[] — KOSIS 셀 미도달 주요 사례**

- 취업자 증감(+/-) 세부 항목: 고용동향 표에서 증감 항목 코드 못 찾음
- 소매판매 세부 업태별 수치: 표 구조 복잡, HCX abstain 또는 objL 재시도 실패
- 합계출산율 등 인구 통계: 검색 키워드 미스매치

### 3-4. HIT 패턴 — 잘 작동하는 케이스

| 유형 | 대표 row | 비고 |
|---|---|---|
| 취업자 수(절대값) | 1, 21, 81, 83, 106 | DT_1DA7001S 안정 |
| 소비자물가지수(절대) | 32, 37, 64, 95 | DT_1J22003 안정 |
| 출생아수/합계출산율 | 15 | DT_1B8000H 안정 |
| 실업률(절대) | 9, 41 | 수치 직접 조회 |
| 소매판매지수(절대) | 52 | 총지수 항목 |

**공통점**: 절대값 + 표 구조 단순(1~2축) + 주요 전국조사 표 + 지수·증감 계산 불필요

## 4. 추가/변경 파일

- `src/modules/map_claim_via_meta.py` — 새 [4+5] 대안 경로
- `src/prompts/prompts.py` — `SELECT_KOSIS_CELL_*`, `GEN_KOSIS_KEYWORDS_*`
- `src/llm/model_presets.py` — `SELECT_KOSIS_CELL`, `GEN_KOSIS_KEYWORDS`
- `.claude/skills/kosis-lookup/SKILL.md` — 절차 명세

## 5. 다음 단계 (개선 우선순위)

### 우선순위 1 — ev=[] 52건 줄이기 (coverage 개선)
- `abstain=True` 비율 확인 (Langfuse `select` generation output)
- 검색 키워드 품질 개선: 증감량 claim → "취업자 증감", "전월 대비" 등 키워드 추가
- KOSIS 표에 변화량 항목(`전월비`, `전년동월차`) 존재 시 우선 선택 규칙 추가

### 우선순위 2 — ev≠gold 49건 줄이기 (정확도 개선)
- 단위 정규화: claim 단위(천명/만명/명) ↔ KOSIS 단위 일치 검증 로직 추가
- 변화율 claim에서 YoY 계산 트리거 조건 개선 (현재 일부 미작동)
- `SELECT_KOSIS_CELL` 프롬프트 튜닝: wrong item 패턴(고용률 선택 오류 등) Langfuse 트레이스로 확인 후 few-shot 추가

### 우선순위 3 — 모델 비교
- 현재 HCX-007(temp=0) → Claude Sonnet/Haiku 등 다른 모델과 `SELECT_KOSIS_CELL` A/B
- Langfuse의 `map_claim_via_meta:select` generation 품질 기준으로 비교
