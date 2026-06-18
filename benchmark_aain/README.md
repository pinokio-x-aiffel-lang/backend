# benchmark_aain — 2~10단계 모듈별 테스트

`src/pipeline/runner.py` 의 **2~10단계 각 모듈을 독립적으로 평가**하기 위한 평가셋·계획.
단계마다 ① 측정 지표 ② 입력 데이터 형태(JSON) ③ 최소 데이터 수 ④ gold 출처·보강을 정의한다.
다른 벤치마크(`benchmark/`)와 섞이지 않도록 분리한 폴더.

> 작성: leeaain · 2026-06-14 (README 통합: 2026-06-18) · 대상: `src/modules/*` 10단계 중 2~10

---

## 단계별 산출 평가지표 (요약)

| 단계 | 모듈 (폴더) | 핵심 지표 | 보조 지표 | 최소 표본 |
|---|---|---|---|---|
| 2 | extract_statistical_claims (`2_claim`) | 문장 **P/R/F1** | claim_type 정확도 · 슬롯 채움 정확도 · coverage | 양성50+음성50 |
| 3 | normalize_claim (`3_normalize`) | **value·period 정규화 정확도** | compare_period 정확도 · 룰/LLM 폴백률 | ~50 |
| 4 | retrieve_kosis_candidates (`4_retrieve`) | **Recall@N / @3 / @1** | MRR · 검색 실패율 | gold_tbl_id ≥50 |
| 5 | fetch_kosis_data (`5_fetch`) | **셀 값 정확도** | itmId 매칭률 · population 폴백률 · 시점 매칭률 | 공식값 ≥30 |
| 6 | rank_evidence (`6_rank`) | **Top-1 정확도** | 기권율 · RANK 베이스라인 대비 개선 | 다중후보 ≥30 |
| 7 | calculate_metric (`7_metric`) | **verdict 정확도 (T/F/N)** | mismatch_type 정확도 · 허용오차 경계 정확도 | 각 클래스 ≥15 |
| 8 | check_alignment (`8_alignment`) | **T vs M 분류 정확도** | mismatch 차원 정확도 · NEI(LLM 실패)율 | T≥30 + M≥30 |
| 9 | decide_verdict (`9_verdict`) | **verdict_counts 정확도** | overall_confidence · coverage (결정적·오차 0 기대) | ~10 그룹 |
| 10 | generate_explanation (`10_explanation`) | **템플릿 설명 정확도** | overall_opinion 품질(루브릭) · 폴백 발생률 | ~15–20 |

각 단계 상세 지표·입력 형태·gold 출처는 아래 [단계별 상세](#단계별-상세-2-10) 참조.

---

## 데이터 / 산출 파일

### 마스터 · 원천
- **`../benchmark/data/260614_master_eval_213_parsed_human_checked_SSOT.jsonl`** — **origin 테스트 소스(SSOT, 정본)**. 213행(T123/F30/M30/NEI30), `row_id` 로 모든 단계 역추적. `benchmark/` 폴더는 이 SSOT 1개만 두고 나머지 자료는 모두 `benchmark_aain/` 로 통합.
- `data/260605_평가셋_T_F_M_NEI_모음.xlsx` — 마스터 라벨링 원본(xlsx).
- `data/260614_capture_master_stage1to8.json` — 마스터 213문장을 1~8단계에 통과시킨 라이브 캡처(입력 재료).
- `data/260617_gold_tbl_id_subset.jsonl` / `…_review.md` — 4·5·6단계용 정답 `tbl_id` 주석 보강분(검수 중).

### 단계별 평가셋 (각 모듈 폴더로 이동 — `<N_모듈>/source.jsonl`)
| 단계 | 파일 | 행수 | 비고 |
|---|---|---|---|
| 2 | `2_claim/source.jsonl` | 313 | 기존 슬롯 gold 100 + 마스터 양성 213 |
| 3 | `3_normalize/source.jsonl` | 100 | 기존 hand-labeled gold 재사용 |
| 4 | `4_retrieve/source.jsonl` | 411 | 후보 캡처. `gold_tbl_id` 주석 보강 필요 |
| 5 | `5_fetch/source.jsonl` | 411 | 캡처 evidence 132건. gold: T=공식값/F·M=캡처값/NEI=없음 |
| 6 | `6_rank/source.jsonl` | 68 | 후보≥2 claim만. `gold_best_index` 15건 도출 |
| 7 | `7_metric/source.jsonl` | 411 | has_evidence 132. gold=라벨(M→T 매핑) |
| 8 | `8_alignment/source.jsonl` | 106 | label∈{T,M}+evidence. T76/M30 |
| 9 | `9_verdict/source.jsonl` | 11 | 결정적 시나리오(라벨+스펙 산식) |
| 10 | `10_explanation/source.jsonl` | 411 | 캡처값+라벨 verdict. 템플릿=스냅샷 비교 |

각 모듈 폴더에는 `source.jsonl`(평가 데이터) 외에 `io.yml`(읽는/쓰는 필드 계약), `io.jsonl`(input/expected 슬라이스 예시 1건)도 둔다.

### 빌드 스크립트 (재생성)
> ⚠️ 아래 스크립트는 위 파일들이 `data/` 에 있을 때 기준 경로로 작성됨. SSOT 이름 변경·source 이동에 맞춰 경로 갱신 필요(미반영).
```bash
uv run python benchmark_aain/build_master_spine.py            # xlsx → 스파인
uv run x  python benchmark_aain/run_capture.py                # 213문장 1~8단계 라이브 캡처
uv run python benchmark_aain/build_eval_sets.py               # 결정적 단계(2·3·9)
uv run python benchmark_aain/build_eval_sets_from_capture.py  # 캡처 기반(4·5·6·7·8·10)
```

---

## 설계 원칙

### 단일 진실 원천(SSOT) · 무생성
- 모든 평가셋은 마스터셋 1개에서 파생, 각 행은 `row_id` 로 마스터 역추적.
- 값은 ①마스터 xlsx ②기존 실제 gold ③라이브 캡처(실제 KOSIS/LLM)에서만 온다. **지어낸 값 없음.**
- 기존 파일은 읽기 전용. 출력은 이 폴더 신규 파일만.

### 2-레이어 구조 (input ≠ gold)
각 행 = `row_id` + **input**(그 단계가 실제로 받는 형태; candidates·evidences 등은 라이브 캡처로만) + **gold**(마스터 라벨/공식값/주석). 상류 버그와 무관하게 "그 모듈만의 성능"을 측정(모듈 격리).

### F·M 공식값 처리 (옵션 ②)
- 공식값(`kosis_value`)은 **라이브 KOSIS 캡처**로 채우고 `*_source` 로 출처 표시 — 모듈 입력/표시용.
- **정답(gold verdict)은 사람 라벨** 그대로 — 캡처값으로 정답을 재정의하지 않는다.
- 안전장치 `consistency_flag`: F는 `기사값 ≠ 캡처값`, M은 `기사값 ≈ 캡처값` 이어야 정합. 어긋나면 자동 채점 대신 **검토 플래그** 분리, 지표는 "플래그 제외/포함" 둘 다 보고.

### 공통 주의 (지표 신뢰성)
- **클래스 불균형**: T 123 vs F/M/NEI 각 30 → 단계별 표본 작아짐(특히 8단계 M=30). **신뢰구간/보수 해석** 명시.
- **도메인 편향**: 전부 조선일보 통계 인용 문장 → 일반화 과신 금지.
- **NEI 활용**: 4·5·6단계에선 NEI 행을 "정답=조회 실패/해당 없음" 음성 케이스로 재활용.

---

## 단계별 상세 (2~10)

### 2단계 · 클레임 추출 (extract_statistical_claims) — `2_claim/source.jsonl`
기사 본문에서 수치 기반 통계 주장을 추출하고 `claim_type` 을 분류한다. (입력: 기사 텍스트 → 출력: `sentences`, `claims`)

**측정 지표**
- 문장 단위 **P/R/F1** — 통계 주장 문장 선별(음성=비수치 문장 포함 필수)
- **claim_type 분류 정확도** — 7유형(absolute/change_rate/ratio/distribution/comparison/metaphoric/verifiable) + none
- **슬롯 채움 정확도** — subject / value_raw / unit / period_raw / population / cited_source
- **추출률(coverage)** — 수치 보유 문장(양성)에서 claim ≥1 추출 비율

**입력 형태**
```json
{"provenance": "claim_extractor_100", "src_id": 1, "label": "positive",
 "claim_type_gold": "증감", "src_text": "올해 우리나라 경제성장률 전망치를 …낮췄다.",
 "gold_n_claims": 1, "gold_claims": [{"claim_id": "clm-0001", "subject": "경제성장률",
 "value": {"raw": "1.5%"}, "unit": "%", "period_value": {"raw": "올해"}, "population": "대한민국"}]}
```
- `claim_extractor_100`: 슬롯 gold 보유(양성50+음성50) → P/R/F1·slot 채점용
- `master`: 마스터 213(전부 수치문장=양성). 슬롯 gold 미주석(null) → coverage만 검증

**최소 수** 양성 50 + hard-negative 50 = **100** (현재: 100 gold + 213 마스터 = 313행). 음성은 마스터에 없어 기존 50 필수.
**gold** `2_claim_extractor_output.jsonl`(기존 gold) + 마스터 텍스트. 보강: 마스터 213 슬롯 gold 미주석.

---

### 3단계 · 정규화 (normalize_claim) — `3_normalize/source.jsonl`
claim 의 value·period·compare_period raw 표현을 표준값으로 정규화(룰 → LLM 폴백).

**측정 지표**
- **value 정규화 정확도** — 절대값/증감(±)/비율/범위/한국어수사 → 표준 수치
- **period 정규화 정확도** — 상대·절대 시점 → `YYYY` / `YYYY-MM` / `YYYY-Qn` / `YYYY-Hn`
- **compare_period 정확도** · **룰 vs LLM 폴백 비율**

**입력 형태**
```json
{"provenance": "normalize_100", "src_id": 1, "row_id": 1, "base": "2025-04",
 "value": {"raw": "2858만9000명"}, "period_value": {"raw": "지난 3월"},
 "compare_period_value": {"raw": "전년 동월"},
 "gold": {"value": {"expected": "28589000", "match": "num", "kind": "절대값"},
          "period": {"expected": "2025-03", "match": "exact"},
          "compare": {"expected": "2024-03", "match": "exact"}}}
```
- `base` = 기사 발행월(상대시점 기준), `match` = 채점 방식(num/exact).

**최소 수** ~50 (현재 **100행**, 기존 hand-labeled gold).
**gold** `3_normalize_claim_100_gold.jsonl`. 보강: 마스터 True행 `gold_figures` 로 확장 가능.

---

### 4단계 · KOSIS 후보 통계표 검색 (retrieve_kosis_candidates) — `4_retrieve/source.jsonl`
claim.subject 로 KOSIS 통합검색 → 후보 통계표 상위 N개. (입력: claims → 출력: `analysis[*].candidates`)

**측정 지표**
- **Recall@N / @3 / @1** — 정답 표가 상위 N 후보 포함 비율
- **MRR** — 정답 표 평균 역순위 · **검색 실패율** — `success=0`(KosisError) 비율

**입력 형태**
```json
{"row_id": 1, "label": "T", "subject": "취업자 수", "unit": "명", "period_type": "M", "population": "대한민국",
 "candidates": [{"rank": 1, "org_id": "101", "tbl_id": "DT_1DA7001S", "tbl_nm": "…", "stat_nm": "경제활동인구조사"}],
 "gold_tbl_id": null, "gold_item_hint": "취업자 수"}
```
**최소 수** 정답 `tbl_id` 주석 claim ≥50 (현재: 후보 캡처 전부, **`gold_tbl_id` 주석 보강 필요** — `data/260617_gold_tbl_id_subset.jsonl` 진행 중).
**gold** 라이브 캡처(candidates). 보강(gap C): 정답 `tbl_id`/`org_id` 주석 전까지 Recall 산출 불가.

---

### 5단계 · KOSIS 셀 값 조회 (fetch_kosis_data) — `5_fetch/source.jsonl`
후보 표에서 claim 좌표(itm/분류축/시점)를 매핑해 한 셀 값 조회. (입력: candidates+claim → 출력: `evidences`)

**측정 지표**
- **셀 값 정확도** — 조회값 == 공식 gold (오차 0/반올림)
- **itmId 매칭률**(기존 병목) · **population 매칭률/폴백률** · **시점 매칭률**

**입력 형태**
```json
{"row_id": 1, "label": "T",
 "claim": {"subject": "취업자 수", "population": "대한민국", "period_type": "M", "period_value_llm": "2025-03", "unit": "명"},
 "candidates": [{"org_id": "101", "tbl_id": "DT_1DA7001S", "tbl_nm": "…"}],
 "captured_evidences": [{"tbl_id": "DT_1DA7001S", "value": 28589.0, "unit": "천명", "period": "202503", "kosis_item_id": "T20"}],
 "gold": {"value": 28589, "unit": "천명", "value_source": "figure", "consistency_flag": "ok"}}
```
**최소 수** 공식값 보유 claim ≥30 (현재: True 123행 충분, F·M 60은 캡처값+정합 플래그).
**gold** True행 공식값(마스터) + F·M 라이브 캡처값 + 라이브 evidences. 보강: 정답 `tbl_id`(4단계 공유).

---

### 6단계 · 증거 랭킹 (rank_evidence) — `6_rank/source.jsonl`
후보 표 중 '가장 적합한 표'를 LLM 1위 선정(값 미사용·주제 적합도). (입력: `evidences`≥2 → 출력: 재정렬)

**측정 지표**
- **Top-1 정확도** — gold 최적 표가 `evidences[0]` 비율
- **기권율** — LLM null 반환 · **RANK 베이스라인 대비 개선**

**입력 형태**
```json
{"row_id": 1, "label": "T",
 "claim": {"subject": "취업자 수", "population": "대한민국", "unit": "명", "period": "M:2025-03"},
 "evidences": [{"tbl_id": "DT_1DA7001S", "value": 28589.0, "axes": ["성별","연령별"]},
               {"tbl_id": "DT_1B040A3", "value": 27450.0, "axes": ["행정구역별"]}],
 "gold_best_index": 0}
```
**최소 수** 후보 ≥2 claim ≥30 (현재: 캡처 의존 — 부족 시 NEI/F·M 포함 확대).
**gold** 라이브 캡처 evidences + True행 공식값(정답 표 도출). 보강(gap C/D): 다중후보 적으면 정답 인덱스 주석.

---

### 7단계 · 통계 수치 비교 판단 (calculate_metric) — `7_metric/source.jsonl`
정규화 주장 수치 ↔ KOSIS 공식 수치 비교 → 일치(T)/불일치(F)/검증불가(N). (ABSOLUTE/VERIFIABLE)

**측정 지표**
- **verdict 정확도** — 출력(T/F/N) vs gold (매핑 아래)
- **mismatch_type 정확도** — magnitude / rounding / direction · **허용오차 경계 정확도**

**입력 형태**
```json
{"row_id": 1, "label": "T", "gold_verdict_stage7": "T",
 "claim": {"value_llm": "28589000", "claim_type": "absolute", "unit": "명"},
 "evidence": {"value": 28589.0, "unit": "천명", "population_fallback": false},
 "evidence_value_source": "figure", "consistency_flag": "ok"}
```
- **gold 매핑(7단계)**: `T→T`, `M→T`(값 일치 → 7단계 T, 8단계서 M 강등), `F→F`, `NEI→N`.

**최소 수** T/F/N 균형 ≥50 (각 ≥15). 현재: T123(+M30→T)/F30/NEI30 충분.
**gold** 마스터 라벨 + 공식값. 보강: 정합 플래그 'mismatch' 행은 검토 분리.

---

### 8단계 · 정합성 판단 (check_alignment) — `8_alignment/source.jsonl`
7단계 T(수치 일치) 건의 '해석'을 재판정. 정합=T, 오도/왜곡=M, LLM 실패=N. (T·M만 대상)

**측정 지표**
- **T vs M 분류 정확도** — 정합 vs 오도/왜곡
- **mismatch 차원 정확도** — subject/population/unit/aggregation/period · **NEI(LLM 실패) 비율**

**입력 형태**
```json
{"row_id": 124, "label": "M",
 "claim": {"sentence": "2024년 합계출산율이 0.75명으로 …", "subject": "합계출산율", "population": "대한민국", "unit": "명", "aggregation": "값", "period_llm": "2024"},
 "evidence": {"table_name": "인구동향조사", "subject": "합계출산율", "population": "전국", "unit": "명", "period": "2024"},
 "gold": {"aligned": false, "dimension": null}}
```
- 대상 = label ∈ {T, M}. `gold.aligned` = `label==T`. evidence 메타 = 라이브 캡처.

**최소 수** 정합(T) ≥30 + 오도(M) ≥30 = ≥60 (현재: M=30 상한, T 30+ → ~60. **신뢰구간 명시**).
**gold** 마스터 라벨 + 캡처 evidence 메타. 보강(gap B): M 30행 오도 **차원(dimension)** 주석.

---

### 9단계 · 종합 분석·검증 결과 생성 (decide_verdict) — `9_verdict/source.jsonl`
claim별 metric.verdict 종합 → 기사 단위 분포·지표 산출(결정적 집계). (입력: claim_results → 출력: summary)

**측정 지표**
- **verdict_counts 정확도** — `{T,F,M,N}` 카운트
- **overall_confidence** = `T/(T+F+M)` (검증된 것 중 사실, N 제외)
- **coverage** = `(T+F+M)/total` · 결정적 산식 → **정확/오차 0 기대**

**입력 형태**
```json
{"group_id": "grp-01", "scenario": "all_213",
 "claim_results": [{"row_id": 1, "verdict": "T"}, {"row_id": 184, "verdict": "F"}],
 "gold": {"verdict_counts": {"T": 123, "F": 30, "M": 30, "N": 30}, "overall_confidence": 0.6721, "coverage": 0.8592}}
```
**최소 수** 다양한 분포 ~10 그룹(경계: 빈/단일/전부 N 포함). 현재: **11 시나리오**.
**gold** 마스터 라벨 + 스펙 산식 독립 계산 → 보강 불필요(결정적).

---

### 10단계 · 설명 생성 (generate_explanation) — `10_explanation/source.jsonl`
claim별 한국어 템플릿 설명(결정적) + 기사 단위 종합 의견(LLM). (입력: verifications+claims → 출력: explanation·overall_opinion)

**측정 지표**
- **템플릿 설명 정확도(결정적)** — verdict별 문구 / 받침 조사(은·는) / 기간 포맷 / 출처 표기
- **overall_opinion 품질** — 분포 반영·verdict 모순 없음·환각 없음(루브릭) · **폴백 발생률**

**입력 형태**
```json
{"row_id": 1, "label": "T",
 "claim": {"subject": "취업자 수", "unit": "명", "period_type": "M", "period_llm": "2025-03"},
 "claim_result": {"verdict": "T", "claim_value": "28589000", "kosis_value": "28589.0", "mismatch_type": null, "evidence": [{"table_name": "경제활동인구조사"}]},
 "gold_template": "기사의 2025년 3월 취업자 수 28589000명은 KOSIS 공식 수치와 일치합니다. (출처: 경제활동인구조사)"}
```
**최소 수** verdict 4종 + 받침/기간 변형 ~15–20 (verdict별 ≥4).
**gold** 마스터 라벨 + 캡처 값 + 결정적 템플릿. 보강: overall_opinion 품질은 루브릭 사람 평가.

---

## 알려진 한계 (정직 보고)
- 라이브 캡처 verdict 분포 = **N 398 / F 13 / T 0** → 현 파이프라인 KOSIS recall이 낮아 evidence 확보가 적음. 5·7·8단계의 **실제 채점 표본은 evidence가 잡힌 행으로 제한**(5·7: 132, 8: 106). gold verdict는 라벨이라 무관하나, 비교 자체는 표본 한정.
- 클래스 불균형(T 우세) + 조선일보 단일 도메인 → 일반화 지표 과신 금지, 신뢰구간 명시.

## 추가 주석 필요 (gold 보강)
- **4·5·6**: 정답 `tbl_id`/`org_id` 주석. 4단계 `gold_tbl_id` 전부 null.
- **6**: `gold_best_index` 미도출분(68 중 15만 도출).
- **8**: M 30행 오도 **차원(dimension)** 주석.
- **5·7**: F·M 캡처값 `consistency_flag` 가 `mismatch`/`no_evidence` 인 행 검토 분리.
