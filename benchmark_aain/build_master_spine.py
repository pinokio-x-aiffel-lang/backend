"""마스터 평가셋(xlsx) → 코드 친화 스파인(jsonl). 읽기전용 파싱, 값 생성 없음.

입력(읽기만):
  benchmark_aain/data/260605_평가셋_T_F_M_NEI_모음.xlsx   (213행: 텍스트/라벨/공식값)
  benchmark/data/from_labeled_true_2~6_source.jsonl       (True 123행 파싱 gold, 재사용)

출력(신규):
  benchmark_aain/data/260614_master_eval_213_parsed.jsonl

각 행: {row_id, label(T/F/M/NEI), text, figure_raw, gold_figures}
  - gold_figures: True 행만 [{period_raw,period,item,value_raw,value}] (기존 파싱본 재사용),
    F/M/NEI 는 null (공식값 미기재 → 지어내지 않음).

규칙: 어떤 기존 파일도 수정하지 않는다. 출력은 benchmark_aain/ 아래 신규 파일만.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
MASTER_XLSX = ROOT / "benchmark_aain/data/260605_평가셋_T_F_M_NEI_모음.xlsx"
PARSED_TRUE = ROOT / "benchmark/data/from_labeled_true_2~6_source.jsonl"
OUT = ROOT / "benchmark_aain/data/260614_master_eval_213_parsed.jsonl"


def _norm_label(v: object) -> str:
    if v is True:
        return "T"
    if v is False:
        return "F"
    s = str(v).strip()
    return {"True": "T", "False": "F", "M": "M", "NEI": "NEI"}.get(s, s)


def _key(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def main() -> None:
    # --- 마스터 읽기(READ-ONLY) ---
    wb = openpyxl.load_workbook(MASTER_XLSX, read_only=True, data_only=True)
    ws = wb["labelled"]
    rows = list(ws.iter_rows(values_only=True))[1:]  # 헤더 제외

    # --- 기존 True 파싱 gold 읽기(READ-ONLY) ---
    parsed = [
        json.loads(ln)
        for ln in PARSED_TRUE.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith(("#", "//"))
    ]
    parsed_by_key = {_key(p.get("claim", "")): p.get("gold") for p in parsed}

    out = []
    for i, r in enumerate(rows, start=1):
        text = (r[0] or "").strip()
        label = _norm_label(r[1] if len(r) > 1 else None)
        fig = r[2] if len(r) > 2 and r[2] else None
        gold_figures = parsed_by_key.get(_key(text)) if label == "T" else None
        out.append({
            "row_id": i,
            "label": label,
            "text": text,
            "figure_raw": fig,
            "gold_figures": gold_figures,
        })

    OUT.write_text(
        "\n".join(json.dumps(o, ensure_ascii=False) for o in out) + "\n",
        encoding="utf-8",
    )

    # --- 검증 리포트(생성 안 함, 카운트만) ---
    from collections import Counter
    dist = Counter(o["label"] for o in out)
    t_with_gold = sum(1 for o in out if o["label"] == "T" and o["gold_figures"])
    print(f"wrote {len(out)} rows -> {OUT.relative_to(ROOT)}")
    print("label dist:", dict(dist))
    print(f"True rows with reused gold_figures: {t_with_gold}/{dist['T']}")


if __name__ == "__main__":
    main()
