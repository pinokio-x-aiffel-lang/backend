---
name: test-convention
description: Use when starting a performance test, writing eval code, or saving test results. Enforces the shared harness — SSOT input, result location (per-module or e2e folder under benchmark/), file naming, per-sample JSONL, and the report MD.
---

# Test Convention (성능 테스트 하니스)

모듈별·e2e 성능을 **모든 팀원이 동일하게** 측정·기록한다. 코드·API·예시는 `benchmark/HARNESS.md`.

## SSOT · 데이터 위치

- **정본 SSOT(사람 라벨)**: `benchmark/data/ssot/260614_master_eval_213_parsed_human_checked_SSOT.jsonl` (213행 · T123/F30/M30/NEI30). 병인님 라벨 xlsx 등 사람 정본도 모두 **`benchmark/data/ssot/`**.
- **테스트셋(입력+정답)**: **`benchmark/data/<N_module>/<N>_source_*.jsonl`** (+ `io.yml`/`io.jsonl` = 읽고/쓰는 필드 계약·예시). 예: `benchmark/data/4_retrieve/4_source_1.jsonl`(입력)·`4_source_2.jsonl`(gold).
- **결과**: `benchmark/<N_module>/` 또는 `benchmark/e2e/` (아래 "결과 저장").
- **값 생성 금지** — 입력=SSOT, 정답=라벨/공식값/주석. 전후 비교를 위해 입력은 고정.
- (참고용 옛 eval·원시 소스는 `benchmark_aain/`. 실사용 아님.)

## 코드 위치

모든 코드는 `benchmark/` **바로 아래**: `scoring.py`(채점기), `reporting.py`(SSOT 로드·저장), `<테스트 스크립트>.py`(단계/e2e 러너). 결과 폴더에는 산출물(jsonl·md)만.

## 결과 저장

- **라우팅**: 단계 N → `benchmark/<N_module>/`, e2e → `benchmark/e2e/`. (모듈 폴더 `1_article … 10_explanation`)
- **파일**(2종, 같은 stem, `save_result()` 가 생성): `<작성자>_<YYMMDD>_<NN>.jsonl` + `.md`. 무엇을 쟀는지는 폴더(단계)+md title 이 담당.
- **`.jsonl`**: 한 줄 = 한 샘플, 실제 생성된 json 스키마(`input`/`output`/`gold` + 채점 필드).
- **`.md`**: title(`#`) 외 `###`만. 순서: 개요 → 테스트 방법 → 성능 수치(표) → 분석 → 개선 전후 비교 → 한계·주의.
- **I/O 계약 검증**: `save_result()` 가 저장 전 `STAGE_IO`(단계별 필수 input 슬라이스 + 채점 필드)로 record 를 검증 — 위반 시 `ContractError`로 저장 거부. 전후 입력이 흔들리거나 채점 필드가 빠지면 즉시 실패.

## 채점·비교

- 단계별 1차 지표 = `scoring.STAGE_SCORERS[stage]` (지표 목록은 HARNESS.md).
- **전후 비교 필수**: 고정 SSOT + 모듈 격리(상류 gold 고정) + 비율은 `wilson_ci` + 분류 단계는 `mcnemar`(paired). 단일 숫자만 비교 금지(작은 표본·불균형 착시).

## 측정 방식 통일 (frozen-독립 · e2e · cascade) — 팀 공통

측정 도구를 단계마다 갈아끼우면 점수가 *모듈 품질*이 아니라 *측정법*을 반영한다 → "개선했는데 점수가 깎이는" 착시가 생긴다. 그래서 **역할별로 한 가지 측정법으로 고정**한다(단계마다 두 코드 왔다갔다 금지).

- **모듈 품질 = `frozen-독립` 한 가지로만.** 독립 입력으로 `MasterSchema` 를 직접 구성 → **그 모듈만** 실행 → 독립 gold 로 채점. 표준 패턴 = `benchmark/eval_stage8.py`, 파일명 `eval_stage<N>_frozen.py`.
  - **입력도 gold 도 둘 다 독립**이어야 한다. gold 만 독립이고 입력이 **파이프라인 캡처**(예 `v2_capture260619`)면, 상류 개선 시 캡처가 stale 해져 모듈을 *옛 상류 출력*으로 채점한다 — "캡처를 얼린 cascade"라 **금지**. 독립 입력 출처: SSOT claim · 병인님 `official_value`·`gold_tbl_id`·`gold_best_index` 등.
  - frozen 은 **입력만 고정**이다. 모듈 내부의 LLM·KOSIS 호출은 그대로 발동(예: 5단계 frozen 도 라이브 KOSIS 호출). 격리 = 입력 독립이지 결정성 아님.
- **e2e = 한 가지(신선 라이브 + 독립 최종 gold).** 제품/사용자 결과 측정용. **모듈 품질로 쓰지 않는다.**
- **cascade(상류 라이브 전파) = 진단 전용.** "어디서 깨지나"만 본다. **품질 점수로 쓰지 않는다** — cascade 점수엔 모듈품질 × 상류상태 × LLM노이즈가 섞여 귀속 불가(같은 모듈이 cascade 0.0 vs 격리 0.46 사례). 모듈 .md 의 1차 지표는 frozen-독립으로 낸다.

요약: **모듈 = frozen-독립 / 제품 = e2e / 진단 = cascade.** 셋의 역할을 섞지 않는다.

## e2e 결과 출력 형식 (필수)

e2e 테스트(`eval_e2e_full.py`) 실행 후에는 **반드시 아래 2개 표로** 보고한다(러너가 둘 다 출력). 비교가 쉽도록 형식·행을 고정한다.

### [표A] 단계별 성적표
컬럼: `단계 | 1차 지표 | 방법 | 평가`. 행 = 단계 **2~9**(각 1행).
- **1차 지표** = `STAGE_SCORERS[단계]` 핵심 수치(예 2=문장 F1(P·R)·ctype, 7=macro-F1·recall[T/F/N], 8=M-recall(M-precision·M-F1)).
- **방법** = `격리` / `frozen-독립` / `value-recall`. cascade 수치는 진단용이라 품질표 단독 인용 금지 — 부득이 쓰면 `🔶` 표시.
- **평가** = ✅/⚠️/❌/△ + 한 줄(병목·해석).

### [표B] e2e funnel
컬럼: `지표 | <실행1> | <실행2> | … | 현재 | 변화(vs 최초)`. 행은 **고정 6개, 순서 고정**:
1. `전체 claim` — 완주 기사의 추출 claim 수
2. `evidence_reach (셀 도달)` — 분자/분모 = %
3. `value_reach (값 도달)` — 분자/분모 = %
4. `coverage (T/F/M 판정)` — 분자/분모 = %  ((T+F+M)/total)
5. `gap (값 왔는데 NEI)` — 분자/분모 = %  (value_reach − coverage)
6. `verdict 분포` — `N…·T…·F…·M…`

- 비율 셀은 **`분자/분모 = %`** 형식(예 `155/392 = 39.5%`).
- **변화 컬럼은 *최초 실행* 대비**(직전 아님) pp 차이 + ↑/↓.
- 권장 1줄 추가: 최종 `macro-F1`(after9 vs 독립 gold) + recall[T/F/N]·M-recall.
- 캡처 비결정성(LLM)으로 단일 숫자는 흔들리니 **CI/macro-F1 중심**으로 읽는다고 명시.

## Gold(정답) 라벨링·보완

테스트셋 gold 가 비거나 부족할 때 채우는 규칙. 핵심은 **비순환(non-circular)**.

- **비순환 원칙**: gold 는 **독립 출처에서만** — SSOT `gold_figures`(사람검수)·병인님 라벨 xlsx·KOSIS raw 확인. 파이프라인이 캡처한 출력값이나 파이프라인 함수(search·map_cell 등)로 gold 를 만들면 순환(자기채점)이라 **금지**(value-scan 류 폐기).
- **결정적 vs 검수필요 분리** — 보완 항목을 둘로 나눠 처리:
  - *결정적*(바로 채움): 기계적 매핑(한글 라벨↔enum), 결정적 계산(기사값 vs 공식값 → `magnitude`/`rounding`), 스펙 스냅샷(`_build_explanation` 템플릿), 파생(4 gold → 6 `gold_best_index`).
  - *검수필요*(해석 개입): %/파생 `mismatch_type`, 텍스트서 추출하는 슬롯(subject/unit/population — 추출기와 오류 겹침), 값-확인 안 되는 델타 기준표. → **초안 + 검수 컬럼 md 표**로 만들어 사람 검수 후 반영.
- **값-기반 채점(표 라벨링 회피)**: 4단계 retrieval 은 정답 '표'를 라벨링하지 않고 **figure 값이 후보표 셀에 실재하는지 KOSIS raw 로 확인**(value-recall) → `gold_rank`=값 최초 발견 순위. 표 유일성 제약·과소평가 제거, 전 T행 채점 가능. 델타(증감)는 단일 셀에 없어 자연 미검출(검색 탓 아님 → 검수필요 델타로 분리).
