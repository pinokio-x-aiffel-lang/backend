"""성능 테스트 하니스 — 팀 공용 평가 프레임워크.

공개 API:
    load_ssot()                              # 고정 SSOT(213행) 로드
    save_result(target, author, records, metrics_rows, sections)  # jsonl+md 저장(라우팅)
    blank_sections()                         # md 섹션 템플릿
    STAGE_SCORERS[stage](records)            # 단계별 채점 → metrics_rows
    scoring.*                                # primitives(prf1·wilson_ci·mcnemar·confusion_md 등)

사용 패턴(작성자 스크립트):
    from benchmark.harness import load_ssot, save_result, blank_sections, STAGE_SCORERS
    rows = load_ssot()
    records = run_my_stage(rows)             # 모듈 격리 실행 → 샘플별 dict
    metrics = STAGE_SCORERS[5](records)
    sec = blank_sections(); sec["개요"] = "..."
    save_result(5, "leeaain", records, metrics, sec)

상세: benchmark/HARNESS.md · 컨벤션 강제: .claude/skills/test-convention
"""
from __future__ import annotations

from . import scoring
from .reporting import (
    BENCH_DIR,
    SSOT_PATH,
    SECTION_KEYS,
    STAGE_FOLDERS,
    STAGE_MODULES,
    blank_sections,
    load_ssot,
    render_md,
    save_result,
)
from .scoring import STAGE_SCORERS

__all__ = [
    "scoring",
    "BENCH_DIR", "SSOT_PATH", "SECTION_KEYS", "STAGE_FOLDERS", "STAGE_MODULES",
    "blank_sections", "load_ssot", "render_md", "save_result", "STAGE_SCORERS",
]
