# from_origin_212 — 1~10단계 E2E 디버깅 결과

## 1. 개요
- 목적: `from_origin_212_source.jsonl`(2단계 통과 claim)을 1→10단계 끝까지 돌려, **어느 단계에서 죽는지**와 **최종까지 살아남는 claim 수**를 센다(디버깅 스모크).
- 입력: `from_origin_212_source.jsonl` — claim 212건 중 고유 기사 **168건**(`source_sentence` 중복 제거).
- 흐름: `Pipeline.run(source_sentence)` (stage 2 재추출 포함 → claim 360건 생성).
- 실행: `uv run x`, 동시 6. 총 1700s(평균 10.1s/건).
- 원자료: `260617_1~10_from-origin-212_leeaain_result.json` (기사별 MasterSchema model_dump).

## 2. 테스트 내용
- 각 기사를 파이프라인 끝까지 실행, 단계 `raise`는 흡수해 실패 단계로 기록하고 계속(스모크).
- 완료 후 claim별로 단계 산출물(`kosis_search`/`candidates`/`cell_attempts`/`evidences`/`verdict`)을 집계해 깔때기를 만든다.

## 3. 지표

### 완주
- 기사 완주(무중단 raise 0): **168/168** — 파이프라인 자체는 끝까지 안 죽음.
- **최종 생존 claim(판정 T/F/M): 3/360 (0.8%)** — 나머지 357은 NEI(`N`).
- 판정 분포: `T`×2, `F`×1, `N`×357.

### 단계별 깔때기 (claim 360 기준)
| 관문 | 통과 | 직전 대비 | 누적 |
|---|---|---|---|
| [2] claim 추출 | 360 | — | 100% |
| [4] KOSIS 표 검색·선택 | 162 | −198 | 45.0% |
| [5] 셀 값 획득(evidence) | 26 | −136 | 7.2% |
| [7~9] 실제 판정(NEI 아님) | 3 | −23 | 0.8% |

### 10단계 전체 통과 수 (claim 360 기준, [1]만 기사 168 단위)
| 단계 | 모듈 | 통과 | 전용 평가셋(gold) | 비고 |
|---|---|---|---|---|
| [1] | load_article | 168 / 168 | `0_origin_50set.txt`, `from_origin_200_source.txt`, `from_origin_212_source.jsonl` (입력만, gold 불필요) | 기사 단위 |
| [2] | extract_statistical_claims | 360 | `2_claim_extractor_50_source.txt` + `2_claim_extractor_output.jsonl` (양성50+음성50 gold) | claim 생성 |
| [3] | normalize_claim | 360 | `3_normalize_claim_100_source.jsonl` + `3_normalize_claim_100_gold.jsonl` | 전건 정규화 성공 |
| [4] | retrieve_kosis_candidates | 162 | `from_labeled_true_2~6_source.jsonl` (정답 표 id 라벨 없음) | 후보표 0건 → 198 탈락 |
| [5] | fetch_kosis_data | 26 | `from_labeled_true_2~6_source.jsonl` (값 gold, **True만** 123건) | 값 획득; 136 실패(itmId 103·rate limit 21·기타 12) |
| [6] | rank_evidence | 26 | — (전용 없음) | evidence 있는 26건만 랭킹 |
| [7] | calculate_metric | 26\* | — (전용 없음) | metric 객체는 360건 채우나 328건은 "KOSIS 매칭 없음" 빈껍데기 |
| [8] | check_alignment | 2 | — (전용 없음) | stage7 `T` 후보만 정합성 LLM 실행(정책상 T만 재판정) |
| [9] | decide_verdict | 360 → T2·F1·N357 | `1_e2e.txt` (T/F/M-S/NEI 라벨, E2E 단위) | 전건 판정 배정, 실판정 3 |
| [10] | generate_explanation | 360 | — (전용 없음) | 전건 설명 생성 |

> 전용 평가셋은 단계 격리 테스트용(`benchmark/data/`)이며 **이번 E2E 런에는 미사용** — 이번 런은 단일 파일 `from_origin_212_source.jsonl` 을 stage 1에 넣어 끝까지 흘렸다([2]~[10]은 직전 단계 산출 in-memory 입력).

\* **주의**: [7]·[9]·[10]은 evidence 유무와 무관하게 **360건 전부에 산출물을 채운다**(NEI 빈값 포함). 위 [7]=26은 "실제 KOSIS 값으로 계산된" 유효 건이고, 나머지 334건은 `metric.note="KOSIS 매칭 없음"`(328)·"검증 대상 아님"(6) 플레이스홀더다.

**실질 깔때기(값이 실제로 흐른 경로)**: 360 →[4] 162 →[5] 26 →[7] 유효 26 →[8] 2 → **실판정 3**(T2·F1).

## 4. 병목·원인 (디버깅 핵심)

병목은 **KOSIS 조회 2곳**이다. LLM 단계(2·3·6·7·8·9·10)는 raise 없이 통과.

### ① [5] 표는 찾았는데 값을 못 가져옴 — 136건 (최대 누수)
| 사유 | 건수 |
|---|---|
| **itmId 미매칭** | **103** |
| 메타/셀 조회 rate limit(40: 1분 호출 초과) | 21 |
| 분류/지역 미매칭 | 7 |
| 데이터 없음(30) | 5 |
- `itmId 미매칭` 103건이 압도적 — 표는 골랐으나 항목(item) 코드를 못 맞춤. (메모리 `kosis-pipeline-recall-baseline`의 "5단계 itmId 미매칭" 병목과 일치.)
- rate limit 21건은 **로직 아님·인프라**: 동시 6으로 돌려 getMeta(ITM+PRD) 버스트가 1분 한도 초과. 동시도 낮추거나 sliding-window lock 점검 시 ~21건 회복 가능.

### ② [4] 표를 아예 못 찾음 — 198건
- 검색 결과 0 또는 표 미선택. 4단계 검색 정확도 문제(기존 베이스라인과 동일 양상).

### ③ 값이 있는데도 NEI — 23건 ⚠️ 버그 의심
- `kosis_value`는 채워졌는데 verdict는 `N`, 설명은 "**KOSIS 공식 통계를 찾지 못해 검증할 수 없습니다**".
- evidence(5단계 값)와 7~9단계 판정 사이 **단절** — 찾은 값이 metric/alignment로 전달·수용되지 못하는 것으로 보임. 단일 단계 격리 재현 필요.

## 5. 결론
- "10단계까지 돌아가나?" → **예, 168/168 무중단.**
- "몇 개나 살아남나?" → **3/360 (0.8%)만 실제 판정**, 나머지는 KOSIS 조회 실패로 NEI.
- 우선순위: **(1) 5단계 itmId 매칭(103건)** → (2) 4단계 검색 정확도(198건) → (3) 값-있는데-NEI 단절(23건, 버그) → (4) rate limit 동시도 조정(21건).
