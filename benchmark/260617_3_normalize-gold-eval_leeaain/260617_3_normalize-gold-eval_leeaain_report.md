# 260617_3_normalize-gold-eval — 3단계 normalize gold 채점

## 1. Overview
3단계 `normalize_claim` 의 정규화 정확도를 gold 100건(`benchmark/data/3_normalize_claim_100_gold.jsonl`)으로 채점하는 신규 스코어러. 기존 채점 스크립트(`tests/eval_normalize_claim.py`)가 소실되어 새로 작성.

## 2. What was tested
두 모드:
- **A (헤드라인)**: gold 의 `raw` 를 **현재 정규화 룰**(`_parse_value`/`_normalize_period`, rule-only·LLM 폴백 미포함)에 통과 → gold `expected` 와 1:1 대조. = 순수 stage-3 정규화 정확도.
- **B (참고)**: gold vs 기존 `3_normalize_claim_100_output.jsonl`(stale 2→3 파이프라인 덤프). id+슬롯 `raw` 매칭 → 매칭분의 정규화 정확도 + 추출 커버리지.

채점: `match='num'`→float 동치(부호 포함) / `match='exact'`→문자열 일치 / gold 슬롯 null 제외.

## 3. Metric results

### 모드 A — 현재 룰 vs gold (실 stage-3 정확도)
| 슬롯 | 정답/전체 | acc |
|---|---|---|
| value | **100 / 100** | **1.000** |
| period_value | 71 / 77 | 0.922 |
| compare_period_value | 17 / 61 | **0.279** |
| **OVERALL** | **188 / 238** | **0.790** |

> 메모리 베이스라인(0.559) 대비 0.79로 상승. value 는 오늘 룰 보강 포함 **만점**. 전체를 끌어내리는 건 `compare_period_value`(0.279).

### 모드 B — 기존 output.jsonl vs gold (참고)
| 슬롯 | raw 매칭(추출 커버리지) | 매칭분 normalize-acc |
|---|---|---|
| value | 32 / 100 | 18/32 = 0.562 |
| period_value | 50 / 77 | 41/50 = 0.82 |
| compare_period_value | **0 / 61** | — |

> output 은 stale 2→3 덤프라 **stage-2 추출 한계가 섞임**: compare 0/61 = 2단계 비교시점 미추출 갭, value 32/100 = 추출 불일치. → gold-vs-output 직접 채점은 stage-3 정규화 지표로 부적합. **모드 A 가 정답 지표.**

## 4. 핵심 원인 분석 (모드 A 오답 50건)

오답 분포: `compare_period_value` 44건 + `period_value` 6건. (value 0건)

### ① compare_period_value 상대표현이 base(발행월)에 앵커됨 — 최대 원인 (~24건)
`전년 동월`/`전년 동기`/`전년 같은 달`/`작년 동기` 의 "동월·동기" 가 **기준 시점(period_value) 이 아니라 base(발행일)** 기준으로 계산됨.
```
id1: period_value=지난 3월(2025-03) → 전년 동월 = 2024-03 (gold)
     그러나 pred = 2024-04  ← base(2025-04)의 전년 동월
```
→ "동월/동기" 는 **period_value 를 앵커로** 잡아야 함. 현재 `_normalize_period(raw, base)` 는 base 만 받아 구조적으로 불가. (compare 정규화에 period_value 전달 필요)
- 같은 계열: `1년 전`(7), `전년`(5), `지난해 같은 기간`(2) 등도 period 미앵커로 오답.

### ② period_value — 연도 없는 단독 '월' 미처리 (3건)
`1월 말`·`2월`·`9월` → `None`. `올해/작년` 수식어 없는 **bare 'N월'** 에 base 연도를 안 붙임. (expected 2025-01/02/09)

### ③ period_value — '올해 상반기' 반기 소실 (1건)
`올해 상반기` → `2025` (expected `2025-H1`). 상대 반기 패턴이 `작년 상반기` 만 있고 `올해 상반기` 누락 → "올해"로만 잡혀 연도화.

### ④ period_value — '작년 말' 규약 불일치 (2건, 판단 필요)
`작년 말` → 룰 `2024-12` vs gold `2024`. 룰이 더 구체적(12월)이라 **버그라기보단 규약 차이** — gold 를 연도로 둘지 룰을 따를지 결정 필요.

## 5. 권장 우선순위
1. **compare 상대표현 period 앵커링**(①, ~24+건) — compare 정규화에 period_value 를 anchor 로 전달. compare acc 0.279→대폭 개선 기대.
2. bare 'N월'·'N월 말' 연도 보강(②, 3건) — `_normalize_period` 에 base 연도 결합 룰.
3. '올해 상반기/하반기' 패턴 추가(③, 1건).
4. '작년 말' 규약 합의(④) — 코드/ gold 중 한쪽 정렬.

원자료·오답 전체: `260617_3_normalize-gold-eval_leeaain_result.json`
