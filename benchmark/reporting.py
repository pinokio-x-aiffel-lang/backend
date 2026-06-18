"""결과 저장·리포트 렌더 — SSOT 로드 + 라우팅 + jsonl/md 작성.

흐름:
    1. load_ssot()                                  # 고정 SSOT 로드
    2. (작성자가 모듈을 격리 실행해 records 생성)         # 단계별 runner
    3. scoring.STAGE_SCORERS[stage](records)         # 채점 → metrics_rows
    4. save_result(stage|'e2e', author, records, metrics_rows, sections)

저장 규칙:
    benchmark/<N_module>/<작성자>_<YYMMDD>_<NN>.jsonl   # 샘플별 실제 생성 스키마
    benchmark/<N_module>/<작성자>_<YYMMDD>_<NN>.md      # 보고서(title + h3) + 수치 표
    e2e 테스트는 benchmark/e2e/ 로.

컨벤션 단일 출처: .claude/skills/test-convention . 사용법: benchmark/HARNESS.md .
"""
from __future__ import annotations

import json
from datetime import date as _date
from pathlib import Path

# benchmark/reporting.py → benchmark/ (data·결과 폴더와 같은 위치)
BENCH_DIR = Path(__file__).resolve().parent
SSOT_PATH = BENCH_DIR / "data" / "260614_master_eval_213_parsed_human_checked_SSOT.jsonl"

STAGE_FOLDERS = {
    1: "1_article", 2: "2_claim", 3: "3_normalize", 4: "4_retrieve", 5: "5_fetch",
    6: "6_rank", 7: "7_metric", 8: "8_alignment", 9: "9_verdict", 10: "10_explanation",
}
STAGE_MODULES = {
    1: "load_article", 2: "extract_statistical_claims", 3: "normalize_claim",
    4: "retrieve_kosis_candidates", 5: "fetch_kosis_data", 6: "rank_evidence",
    7: "calculate_metric", 8: "check_alignment", 9: "decide_verdict", 10: "generate_explanation",
}

# md 섹션 순서 (title 외 전부 h3). "성능 수치"(수치 표)는 render_md 가 자동 삽입.
SECTION_KEYS = ["개요", "테스트 방법", "분석", "개선 전후 비교", "한계·주의"]


def blank_sections() -> dict:
    return {k: "" for k in SECTION_KEYS}


def load_ssot() -> list:
    """고정 SSOT(213행) 로드. 모든 평가의 단일 입력 원천."""
    with SSOT_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _today() -> str:
    return _date.today().strftime("%y%m%d")


def _target_folder(target) -> Path:
    if target == "e2e":
        return BENCH_DIR / "e2e"
    if isinstance(target, int) and target in STAGE_FOLDERS:
        return BENCH_DIR / STAGE_FOLDERS[target]
    raise ValueError(f"target 은 1..10 정수 또는 'e2e' 여야 합니다. got {target!r}")


def _next_seq(folder: Path, author: str, date: str) -> int:
    """같은 폴더·작성자·날짜의 다음 순번(NN). 기존 최대 +1."""
    n = 0
    for p in folder.glob(f"{author}_{date}_*.jsonl"):
        try:
            n = max(n, int(p.stem.split("_")[-1]))
        except ValueError:
            continue
    return n + 1


def _md_table(rows: list) -> str:
    if not rows:
        return "_(지표 없음)_"
    cols = list(rows[0].keys())
    head = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join(["---"] * len(cols)) + "|"
    body = ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in rows]
    return "\n".join([head, sep, *body])


def render_md(title: str, sections: dict, metrics_rows: list) -> str:
    """title 외 전부 h3. 순서: 개요 → 테스트 방법 → 성능 수치(표) → 분석 → 개선 전후 비교 → 한계·주의."""
    parts = [f"# {title}", ""]
    for k in ["개요", "테스트 방법"]:
        parts += [f"### {k}", (sections.get(k, "") or "").strip() or "_(작성 필요)_", ""]
    parts += ["### 성능 수치", _md_table(metrics_rows), ""]
    for k in ["분석", "개선 전후 비교", "한계·주의"]:
        parts += [f"### {k}", (sections.get(k, "") or "").strip() or "_(작성 필요)_", ""]
    return "\n".join(parts).rstrip() + "\n"


def save_result(target, author: str, records: list, metrics_rows: list,
                sections: dict, *, title: str | None = None, date: str | None = None) -> tuple[Path, Path]:
    """결과 2종(jsonl·md)을 라우팅 폴더에 저장하고 경로를 반환.

    target  : 단계 정수(1..10) | 'e2e'
    records : 샘플별 실제 생성 스키마(jsonl 한 줄씩)
    metrics_rows: scoring.py scorer 결과 → md '성능 수치' 표
    sections: blank_sections() 채운 dict(개요/테스트 방법/분석/개선 전후 비교/한계·주의)
    """
    folder = _target_folder(target)
    folder.mkdir(exist_ok=True)
    date = date or _today()
    nn = _next_seq(folder, author, date)
    stem = f"{author}_{date}_{nn:02d}"

    jsonl_path = folder / f"{stem}.jsonl"
    md_path = folder / f"{stem}.md"

    with jsonl_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    if title is None:
        title = (f"{stem} — e2e 성능 평가" if target == "e2e"
                 else f"{stem} — [{target}] {STAGE_MODULES[target]} 성능 평가")
    md_path.write_text(render_md(title, sections, metrics_rows), encoding="utf-8")
    return jsonl_path, md_path
