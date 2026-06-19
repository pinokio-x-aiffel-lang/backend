---
description: 벤치마크 단계/e2e 테스트를 공용 하니스 규약대로 실행하고 결과를 저장
argument-hint: <단계번호|e2e> [작성자]
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

벤치마크 테스트를 **반드시 아래 규약대로** 실행하고 결과를 기록한다.
상세·단일 출처: `.claude/skills/test-convention` 스킬과 `benchmark/HARNESS.md`.

대상: **$ARGUMENTS** (예: `4` 또는 `e2e`. 작성자 미지정 시 사용자에게 묻거나 기본값 사용)

## 반드시 지킬 것 (확실히 적용)
1. **입력은 SSOT만**: `benchmark/data/260614_master_eval_213_parsed_human_checked_SSOT.jsonl`. 값 생성 금지.
2. **채점·저장은 하니스로만**: 채점=`benchmark/scoring.py`의 `STAGE_SCORERS[단계]`, 저장=`benchmark/reporting.py`의 `save_result()`. **파일명·경로를 손으로 만들지 말 것 — save_result가 라우팅·네이밍·검증을 처리.**
3. **결과 저장 위치**: 단계 N → `benchmark/<N_module>/`, e2e → `benchmark/e2e/`. (산출물 전용 폴더)
4. **파일 2종**(같은 stem, save_result가 생성):
   - `<작성자>_<YYMMDD>_<NN>.jsonl` — 샘플별 **실제 생성 json 스키마**(`input`/`output`/`gold` + 채점 필드)
   - `<작성자>_<YYMMDD>_<NN>.md` — 보고서. **title(`#`) 외에는 `###`(h3)만.** 순서: 개요 → 테스트 방법 → 성능 수치(표) → 분석 → 개선 전후 비교 → 한계·주의
5. **비순환 필수**: gold(정답)는 **독립 출처에서만** — SSOT figure · 병인님 라벨 · KOSIS 값-확인. **파이프라인 캡처값을 gold로 쓰지 말 것**(예측으로만 사용). 위반 시 멈추고 보고.
6. **단계별 지표**(우리가 정한 것): 2=문장 P/R/F1 · 3=value/period accuracy · 4=Recall@N·MRR · 5=셀값 accuracy×coverage · 6=Top-1·Δ vs baseline · 7=macro-F1+클래스별 recall · 8=M-recall/precision · 9=exact-match · 10=템플릿 accuracy.
7. **전후 비교**: 고정 SSOT + 모듈 격리(상류 gold 고정) + 비율은 `wilson_ci` + 분류는 `mcnemar`(paired).

## 절차
1. 대상 단계의 테스트셋(`benchmark/data/<N_module>/<N>_source_*.jsonl`)과 gold를 확인. 충분성 부족하면 먼저 보고. (SSOT 정본=`benchmark/data/ssot/`)
2. 모듈을 격리 실행(또는 캡처 예측)해 샘플별 record 생성 → `STAGE_SCORERS[단계]`로 채점.
3. `save_result(단계, 작성자, records, metrics_rows, sections)` 로 저장.
4. **저장 경로 + 핵심 지표**를 사용자에게 보고.

## 실행
`uv run x python ...` (시크릿 주입). `scoring`/`reporting`은 `from benchmark.scoring import …` / `from benchmark.reporting import …`.
