"""병인님 xlsx(독립 사람 라벨) → row_id 매칭 → 독립 gold 적용.

비순환: 모든 값/라벨은 병인님 사람 라벨(파이프라인 캡처 아님).
  - F (False 시트):  KOSIS표명 + 원래 공식값
  - M (M-S 시트):    KOSIS표명 + 원래 공식값 + 왜곡기법(=8단계 dimension gold)

출력/적용:
  - benchmark_aain/data/byungin_gold_map.jsonl   # row_id→{label,table_name,official_value,distortion}
  - 8_alignment/8_source_1.jsonl 의 M record gold.dimension ← 왜곡기법(provenance=byungin)

실행: uv run x python benchmark_aain/build_byungin_gold.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
SSOT = ROOT / "benchmark/data/260614_master_eval_213_parsed_human_checked_SSOT.jsonl"
XLSX = ROOT / "benchmark_aain/data/from_origin_with_period_123_source_병인님라벨링.xlsx"
STAGE8 = ROOT / "benchmark_aain/8_alignment/8_source_1.jsonl"
OUT_MAP = ROOT / "benchmark_aain/data/byungin_gold_map.jsonl"


def _norm(s) -> str:
    return re.sub(r"[\s·\-—–~,'’\"()]", "", str(s or ""))


def _parse_value(raw: str):
    """'238,300명 (2024년)' → 238300.0 ; '0.75명 (...)' → 0.75."""
    m = re.search(r"-?\d[\d,]*\.?\d*", str(raw or ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def load_ssot():
    return [json.loads(s) for ln in SSOT.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def match_row_id(text: str, ssot_norm: list[tuple[str, dict]]):
    bn = _norm(text)[:25]
    if not bn:
        return None
    for sn, row in ssot_norm:
        if sn[:25] == bn or sn.startswith(bn) or bn.startswith(sn[:25]):
            return row
    return None


def load_byungin():
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    out = []
    for sheet, lab, has_dist in [("False", "F", False), ("M-S", "M", True)]:
        for r in list(wb[sheet].iter_rows(values_only=True))[1:]:
            if not r or not r[0] or len(r) < 3 or not r[1]:
                continue
            out.append({
                "label": lab, "text": str(r[0]),
                "table_name": str(r[1]).strip(),
                "value_raw": str(r[2]) if r[2] is not None else None,
                "distortion": (str(r[3]).strip() if has_dist and len(r) > 3 and r[3] else None),
            })
    wb.close()
    return out


def main() -> None:
    ssot = load_ssot()
    ssot_norm = [(_norm(r["text"]), r) for r in ssot]
    byungin = load_byungin()

    mapped, unmatched = [], []
    for b in byungin:
        row = match_row_id(b["text"], ssot_norm)
        if row is None:
            unmatched.append(b)
            continue
        mapped.append({
            "row_id": row["row_id"], "label": b["label"],
            "ssot_label": row["label"],
            "byungin_table": b["table_name"],
            "official_value": _parse_value(b["value_raw"]),
            "official_value_raw": b["value_raw"],
            "distortion": b["distortion"],
            "provenance": "byungin",
        })
    OUT_MAP.write_text("\n".join(json.dumps(m, ensure_ascii=False) for m in mapped) + "\n", encoding="utf-8")
    print(f"병인님 {len(byungin)}건 → 매칭 {len(mapped)} / 미매칭 {len(unmatched)}")
    lab_chk = sum(1 for m in mapped if m["label"] != m["ssot_label"])
    print(f"라벨 불일치(검토필요): {lab_chk}")
    if unmatched:
        print("미매칭 예시:", [b["text"][:30] for b in unmatched[:5]])

    # ── 8단계 dimension ← 병인님 왜곡기법 적용 ──
    dist_by_row = {m["row_id"]: m["distortion"] for m in mapped if m["label"] == "M" and m["distortion"]}
    rows = [json.loads(s) for ln in STAGE8.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]
    applied = 0
    for r in rows:
        if r.get("label") == "M" and r["row_id"] in dist_by_row:
            g = r.setdefault("gold", {})
            g["dimension"] = dist_by_row[r["row_id"]]
            g["dimension_provenance"] = "byungin"        # 사람 gold (claude_draft 대체)
            g.pop("dimension_confidence", None)
            applied += 1
    STAGE8.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"8단계 dimension ← 왜곡기법 적용: {applied} record")


if __name__ == "__main__":
    main()
