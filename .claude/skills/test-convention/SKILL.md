---
name: test-convention
description: Use whenever starting a new performance test, writing eval/test code, or saving test results. Enforces the shared performance harness — SSOT input, where results live (per-module or e2e folder under benchmark/), file naming, the per-sample JSONL, and the readable report MD.
---

# Test Convention (성능 테스트 하니스)

모듈별·e2e 성능을 **모든 팀원이 동일한 방식**으로 측정·기록한다.
코드: `benchmark/harness/` 패키지. 사용법: `benchmark/HARNESS.md`.

## SSOT (단일 입력 원천)

모든 평가의 입력은 **단 하나**:
`benchmark/data/260614_master_eval_213_parsed_human_checked_SSOT.jsonl` (213행 · T123/F30/M30/NEI30).
전후 비교가 성립하려면 입력이 고정이어야 한다. **값 생성 금지** — 입력은 SSOT, 정답은 라벨/공식값/주석에서만.

## 결과 위치 (라우팅)

| 테스트 대상 | 저장 폴더 |
| --- | --- |
| 단계 N 모듈 (예: 5단계 fetch_kosis_data) | `benchmark/<N_module>/` (예: `benchmark/5_fetch/`) |
| e2e (전 파이프라인) | `benchmark/e2e/` |

모듈 폴더: `1_article 2_claim 3_normalize 4_retrieve 5_fetch 6_rank 7_metric 8_alignment 9_verdict 10_explanation`.

## 파일 (2종, 같은 stem)

```
benchmark/<N_module>|e2e/<작성자>_<YYMMDD>_<NN>.jsonl
benchmark/<N_module>|e2e/<작성자>_<YYMMDD>_<NN>.md
```

- `<작성자>` 영문 id, `<YYMMDD>` 실행일, `<NN>` 같은 폴더·작성자·날짜 순번(`01`,`02`…).
- 무엇을 쟀는지는 **폴더(단계) + md title** 이 담당(파일명에 topic 없음).
- 직접 만들지 말고 `save_result()` 가 네이밍·라우팅을 처리한다.

### `.jsonl` — 샘플별 실제 생성 스키마

한 줄 = 한 샘플. 테스트하며 **실제로 생성된 json 스키마**(`input`/`output`/`gold` + scorer 채점 필드)를 기록. 디버깅·재채점용.

### `.md` — 보고서

**title(`#`) 외에는 `###`(h3)만** 사용. 순서: 개요 → 테스트 방법 → 성능 수치(표) → 분석 → 개선 전후 비교 → 한계·주의. `render_md()` 가 골격·수치 표를 생성하고, 분석 narrative 는 작성자가 채운다.

## 채점 (지표)

단계별 1차 지표는 `benchmark/harness/scoring.py` 의 `STAGE_SCORERS[stage]` 가 산출한다:
2=문장 P/R/F1(+claim_type) · 3=value·period·compare_period accuracy · 4=Recall@N·MRR · 5=셀값 accuracy×coverage · 6=Top-1·Δ vs baseline · 7=macro-F1+클래스별 recall · 8=M-recall/precision · 9=exact-match · 10=템플릿 accuracy.

**전후 비교 필수**: 고정 SSOT + 모듈 격리(상류 gold 고정) + 비율 지표 `wilson_ci` + 분류 단계 `mcnemar`(paired). 단일 숫자만 비교하지 말 것(작은 표본·클래스 불균형 착시).

## 사용 (요약)

```python
from benchmark.harness import load_ssot, save_result, blank_sections, STAGE_SCORERS
rows = load_ssot()
records = [run_stage_isolated(r) for r in rows]   # 모듈 격리 실행 → 샘플별 dict
metrics = STAGE_SCORERS[5](records)
sec = blank_sections(); sec["개요"] = "..."
save_result(5, "leeaain", records, metrics, sec)  # → benchmark/5_fetch/leeaain_YYMMDD_NN.{jsonl,md}
```

실행은 `uv run x` (시크릿 주입). 상태 점검: `python -m benchmark.harness`.
