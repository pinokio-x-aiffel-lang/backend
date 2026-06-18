---
name: test-convention
description: Use when starting a performance test, writing eval code, or saving test results. Enforces the shared harness — SSOT input, result location (per-module or e2e folder under benchmark/), file naming, per-sample JSONL, and the report MD.
---

# Test Convention (성능 테스트 하니스)

모듈별·e2e 성능을 **모든 팀원이 동일하게** 측정·기록한다. 코드·API·예시는 `benchmark/HARNESS.md`.

## SSOT (단일 입력)

입력은 **단 하나**: `benchmark/data/260614_master_eval_213_parsed_human_checked_SSOT.jsonl` (213행 · T123/F30/M30/NEI30).
**값 생성 금지** — 입력=SSOT, 정답=라벨/공식값/주석. 전후 비교를 위해 입력은 고정.

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
