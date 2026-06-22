"""[8] check_alignment 격리 평가셋 추출 — 원천소스(SSOT + 병인님)에서.

문제: cascade 평가는 M행이 verdict=T를 못 만들어 alignment가 아예 안 돎(M-recall 0).
해결: '수치는 맞아 T가 되지만 프레이밍이 왜곡(M)' 입력을 직접 구성 → alignment 실제 실행.
  - claim.sentence = SSOT 원문(왜곡 맥락 포함) ← 기존 8_source_1의 중립 원자문장 대체
  - evidence = 독립 공식값(T: SSOT gold_figure / M: 병인님 official) → 수치 일치 → verdict=T 유도
  - gold = aligned(label!=M) + dimension(병인님 왜곡기법)
비순환: gold=SSOT 라벨·병인님(독립). claim/evidence 슬롯은 입력(상류 gold)으로 SSOT/병인님서 구성.
IO계약(io.yml record_fields): row_id·label·claim_id·claim·evidence·gold·scorable·scorable_reason.

실행: uv run x python benchmark_aain/build_stage8_eval.py  (LLM/KOSIS 불필요)
출력: benchmark/data/8_alignment/8_source_3.jsonl
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SSOT = ROOT / "benchmark/data/ssot/260614_master_eval_213_parsed_human_checked_SSOT.jsonl"
BYUNGIN = ROOT / "benchmark_aain/data/byungin_gold_map.jsonl"
OUT = ROOT / "benchmark/data/8_alignment/8_source_3.jsonl"

_UNITS = ["명", "원", "%", "호", "건", "세", "가구", "대", "년", "조원", "만원"]
_REGIONS = ["서울", "세종", "경기", "부산", "대구", "인천", "광주", "대전", "울산", "강원",
            "충북", "충남", "전북", "전남", "경북", "경남", "제주"]


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def parse_period(raw):
    m = re.search(r"(\d{4})\s*년", str(raw or "")) or re.search(r"(\d{4})", str(raw or ""))
    return m.group(1) if m else ""


def parse_unit(raw):
    for u in _UNITS:
        if u in str(raw or ""):
            return u
    return ""


def population_of(text, table):
    for r in _REGIONS:
        if r in str(table or "") or r in str(text or "")[:40]:
            return r
    if "농가" in str(table or "") + str(text or "")[:40]:
        return "농가"
    if "청년" in str(text or "")[:40] or "15~29" in str(text or ""):
        return "청년층"
    return "대한민국"


def subject_of(table):
    s = str(table or "")
    return s.split("—")[-1].strip() if "—" in s else s.strip()


def main():
    ssot = {r["row_id"]: r for r in load(SSOT)}
    byungin = {r["row_id"]: r for r in load(BYUNGIN)}

    records = []
    # ── M (30): 왜곡 맥락 + 공식값 일치 → alignment가 M 잡아야 ──
    for rid, b in byungin.items():
        if b["label"] != "M":
            continue
        row = ssot.get(rid)
        if not row:
            continue
        text = row["text"]
        subj = subject_of(b["byungin_table"])
        period = parse_period(b["official_value_raw"])
        unit = parse_unit(b["official_value_raw"])
        pop = population_of(text, b["byungin_table"])
        records.append({
            "row_id": rid, "label": "M", "claim_id": "clm-0001",
            "claim": {"sentence": text, "subject": subj, "population": pop,
                      "unit": unit, "aggregation": "값", "period_llm": period},
            "evidence": {"table_name": b["byungin_table"], "subject": subj, "population": pop,
                         "unit": unit, "period": period, "value": b["official_value"],
                         "population_fallback": False},
            "gold": {"aligned": False, "dimension": b["distortion"], "dimension_provenance": "byungin"},
            "scorable": True, "scorable_reason": "ok(왜곡맥락+공식값일치→T유도)",
            "provenance": "ssot+byungin",
        })

    # ── T (123): 수치 정확 + 프레이밍 정상 → alignment가 T 유지해야(M-precision) ──
    for rid, row in ssot.items():
        if row["label"] != "T":
            continue
        figs = row.get("gold_figures") or []
        if not figs:
            continue
        f = figs[0]
        v = f.get("value")
        if isinstance(v, list):
            v = v[0] if v else None
        subj = str(f.get("item", "")).strip()
        records.append({
            "row_id": rid, "label": "T", "claim_id": "clm-0001",
            "claim": {"sentence": row["text"], "subject": subj,
                      "population": population_of(row["text"], subj),
                      "unit": parse_unit(f.get("value_raw")), "aggregation": "값",
                      "period_llm": str(f.get("period", ""))},
            "evidence": {"table_name": f"{subj} (KOSIS)", "subject": subj,
                         "population": population_of(row["text"], subj),
                         "unit": parse_unit(f.get("value_raw")), "period": str(f.get("period", "")),
                         "value": v, "population_fallback": False},
            "gold": {"aligned": True},
            "scorable": True, "scorable_reason": "ok(수치정확+정상프레이밍→T유지 기대)",
            "provenance": "ssot_figure",
        })

    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
    import collections
    print(f"추출 {len(records)}행 → {OUT}")
    print("  label:", dict(collections.Counter(r["label"] for r in records)))
    print("  gold_M(aligned=False):", sum(1 for r in records if not r["gold"]["aligned"]))
    print("\n샘플 M:")
    print("  ", json.dumps(records[0], ensure_ascii=False)[:400])


if __name__ == "__main__":
    main()
