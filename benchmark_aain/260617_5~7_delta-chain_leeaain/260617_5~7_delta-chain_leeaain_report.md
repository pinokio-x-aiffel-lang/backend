# 260617_5~7_delta-chain_leeaain — 증감 체인 배선 전/후 값 recall

## 1. 개요
증감형(CHANGE_RATE) claim 은 단일 셀조회로는 레벨값만 얻어 gold(전년대비 증감)와 어긋난다(베이스라인 1/105). 본 PR 은 [5] fetch_kosis_data 가 같은 좌표를 기준 시점으로 한 번 더 조회하고 [7] compute_change 가 (현재−기준) 증감을 계산하도록 배선했다. 동일 표 해소에서 단일값(before) vs 증감차(after) 를 함께 채점한다.

## 2. 무엇을 테스트했나
- 채점 대상: T-figure delta 행 + 구체 시점(YYYY/YYYY-MM) **75건** (period 현재/불명 제외, 전부 전년동월/전년 계열).
- 비교 기준 = period − 1년(같은 달). 값 일치 = 단위보정 후 상대오차 ≤2%.
- 기준 시점 evidence 확보 행: 23/75, 에러 0.

## 3. 결과 — 배선 전/후

| 지표 | 배선 전(before) | 배선 후(after) |
|---|---|---|
| delta 값 recall | **0.013** (1/75) | **0.067** (5/75) |

- 증감차 경로 적중(value−compare): **4/75**  (그중 부호까지 일치: 4/75)
- 증감 체인으로 **새로 회수된 행: 4/75** (before miss → after hit)

## 4. 한계 / 범위
- claim.value(주장 수치)가 평가셋에 없어 **값 재현율**만 측정(stage 7 T/F 판정 별도).
- value_matches 는 부호 무시(크기) — baseline 과 동일 기준. signed-hit 를 보조로 병기.
- 후보 top-N 고정(stage 4 재검색 생략). 정답 표가 후보에 없던 행은 구조적 miss.
- 직접 증감-item 매칭 행은 단일값이 이미 gold → before/after 모두 hit(증감차 무관).