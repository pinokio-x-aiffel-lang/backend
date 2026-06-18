# 성능 테스트 하니스 (팀 공용)

모듈별·e2e 성능을 **동일한 방식으로** 측정·기록하기 위한 공용 프레임워크.
컨벤션 강제는 `.claude/skills/test-convention` 스킬, 코드는 `benchmark/` 바로 아래(`scoring.py`·`reporting.py`).

## 구조

```
benchmark/
  scoring.py                   # 채점기(순수 함수): prf1·recall@k·macro_f1·wilson_ci·mcnemar·score_*
  reporting.py                 # SSOT 로드 + 라우팅 + jsonl/md 저장 (load_ssot·save_result·blank_sections·render_md)
  <테스트 스크립트>.py           # 단계/e2e 러너 (모듈 격리 실행 → records 생성 → 채점·저장)
  data/
    260614_master_eval_213_parsed_human_checked_SSOT.jsonl   # SSOT (정본, 213행 T123/F30/M30/NEI30)
  1_article/ … 10_explanation/ , e2e/                        # 결과만 저장
```

모든 코드는 `benchmark/` 바로 아래에 둔다 — 결과 폴더(`<N_module>`·`e2e`)에는 산출물(jsonl·md)만.

## SSOT (단일 입력 원천)

모든 평가는 `benchmark/data/…_SSOT.jsonl` 한 파일에서만 입력을 받는다. 전후 비교가 성립하려면 입력이 고정이어야 한다. 새 값 생성 금지.

## 사용법

프로젝트 루트에서 `uv run x` 로 실행한다(KOSIS_API_KEY·HCX 등 주입). 작성자는 **모듈을 격리 실행**해 샘플별 record 를 만들고, 채점·저장은 하니스에 맡긴다.

```python
from benchmark.scoring import STAGE_SCORERS
from benchmark.reporting import load_ssot, save_result, blank_sections

rows = load_ssot()                       # 고정 SSOT

records = []                             # 샘플별 "실제 생성된 json 스키마"
for row in rows:
    out = run_stage5_isolated(row)       # 모듈 격리 실행(상류는 gold 고정)
    records.append({
        "row_id": row["row_id"], "stage": 5, "label": row["label"],
        "input": out.input_slice, "output": out.produced,   # 실제 생성 스키마
        "gold": out.gold,
        # ↓ scorer 가 읽는 채점 필드 (scoring.py 각 score_* docstring 참고)
        "answered": out.answered, "cell_correct": out.cell_correct,
        "itm_match": out.itm_match, "pop_match": out.pop_match, "period_match": out.period_match,
    })

metrics = STAGE_SCORERS[5](records)      # → metrics_rows

sec = blank_sections()
sec["개요"] = "5단계 fetch_kosis_data 셀 조회 정확도/커버리지 평가."
sec["테스트 방법"] = "모듈 격리(4단계 gold tbl_id 고정), SSOT 213행."
sec["분석"] = "…강점/약점/오류 원인…"
sec["한계·주의"] = "evidence 확보 행만 정확도 분모. 클래스 불균형 신뢰구간 명시."

jsonl, md = save_result(5, "leeaain", records, metrics, sec)
print(jsonl, md)   # → benchmark/5_fetch/leeaain_<YYMMDD>_NN.jsonl / .md
```

import 방식: 프로젝트 루트에서 실행 시 `from benchmark.scoring import …` / `from benchmark.reporting import …`. 스크립트를 `benchmark/` 안에 두고 직접 실행하면 `import scoring, reporting` (형제 모듈).

## 결과 저장 규칙

- **라우팅**: 단계 N 모듈 테스트 → `benchmark/<N_module>/` , e2e → `benchmark/e2e/` .
- **파일명**: `<작성자>_<YYMMDD>_<NN>` (jsonl·md 동일 stem). `NN` = 같은 폴더·작성자·날짜 순번(01,02…). 무엇을 쟀는지는 **폴더(단계) + md title** 이 담당.
- **`.jsonl`**: 한 줄 = 한 샘플. 테스트하며 **실제로 생성된 json 스키마**(`input`/`output`/`gold` + 채점 필드)를 기록 → 디버깅·재채점 가능.
- **`.md`**: 보고서. **title(#) 외에는 `###`(h3)만** 사용. 순서 = 개요 → 테스트 방법 → 성능 수치(표) → 분석 → 개선 전후 비교 → 한계·주의. `render_md` 가 자동 생성하며 분석 narrative 는 작성자가 채운다.

## 단계별 1차 지표 (scoring.STAGE_SCORERS)

| 단계 | 모듈 | 1차 지표 | 보조 |
|---|---|---|---|
| 2 | extract_statistical_claims | 문장 **P/R/F1** | claim_type accuracy·macro-F1 |
| 3 | normalize_claim | **value·period·compare_period accuracy** (각 분리) | 룰 커버리지 |
| 4 | retrieve_kosis_candidates | **Recall@1/3/10 · MRR** | 검색 실패율 |
| 5 | fetch_kosis_data | **셀값 accuracy × coverage** | itmId/population/시점 매칭률 |
| 6 | rank_evidence | **Top-1 accuracy · Δ vs RANK** | 기권율 |
| 7 | calculate_metric | **macro-F1 + 클래스별 recall** | mismatch_type accuracy (+`confusion_md`) |
| 8 | check_alignment | **M-recall · M-precision · M-F1** | NEI(LLM 실패)율 |
| 9 | decide_verdict | **exact-match** (결정적, 오차 0) | — |
| 10 | generate_explanation | **템플릿 accuracy (snapshot)** | opinion은 고정 루브릭(별도) |

## 전후 비교 방법론 (필수)

성능"평가"가 착시가 되지 않도록 리포트에 강제한다:

- **고정 SSOT** — 전후 동일 입력.
- **모듈 격리** — 상류는 gold 입력 고정 → 변화가 그 단계 덕인지 귀속.
- **신뢰구간** — 비율 지표는 `wilson_ci` (n=30 표본에서 70→75%가 노이즈인지 판별).
- **paired 검정** — 분류 단계(2·7·8) 전후 비교는 `mcnemar(before_correct, after_correct)` (χ²>3.84 → 5% 유의). `개선 전후 비교` 섹션에 b(퇴행)/c(개선)/χ² 기재.
