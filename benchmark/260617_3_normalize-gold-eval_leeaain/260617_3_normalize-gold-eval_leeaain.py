"""3단계 normalize_claim gold 채점 스코어러.

gold = benchmark/data/3_normalize_claim_100_gold.jsonl (raw + expected, 100건)
두 모드로 채점:

  A) gold.raw → 현재 정규화 룰(_parse_value/_normalize_period) → gold.expected 대조.
     = 순수 stage-3 정규화 정확도(rule-only, LLM 폴백 미포함). 1:1 정렬.
  B) gold vs 기존 output.jsonl(3_normalize_claim_100_output.jsonl, stale 2→3 파이프라인).
     id+슬롯 raw 매칭 → 매칭분의 정규화 정확도 + 추출 커버리지.
     compare 0/61 등 stage-2 추출 갭이 섞이므로 보조 지표.

채점 규칙:
  match='num'   → float 동치(부호 포함). 변환 불가 시 문자열 일치로 폴백.
  match='exact' → 문자열 일치(strip).
  gold 슬롯이 null 이면 채점 제외.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.modules.normalize_claim import _normalize_period, _parse_value

DATA = Path("benchmark/data")
GOLD = DATA / "3_normalize_claim_100_gold.jsonl"
OUTPUT = DATA / "3_normalize_claim_100_output.jsonl"
SLOTS = ["value", "period_value", "compare_period_value"]


def load_gold() -> list[dict]:
    rows = []
    for ln in GOLD.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("//"):
            continue
        rows.append(json.loads(ln))
    return rows


def load_output() -> dict[int, dict]:
    body = "\n".join(
        l for l in OUTPUT.read_text(encoding="utf-8").splitlines()
        if not l.lstrip().startswith("#")
    )
    return {o["id"]: o for o in json.loads(body)["results"]}


def normalize(slot: str, raw: str, base: str) -> str | None:
    """현재 룰로 슬롯 정규화."""
    if slot == "value":
        return _parse_value(raw)
    return _normalize_period(raw, base)


def is_match(expected: str, pred: str | None, match: str) -> bool:
    if pred is None:
        return False
    e, p = str(expected).strip(), str(pred).strip()
    if match == "num":
        try:
            return abs(float(e) - float(p)) < 1e-9
        except ValueError:
            return e == p
    return e == p


def out_raw_value(o: dict, slot: str, raw: str) -> str | None:
    """output 한 id 안에서 slot.raw==raw 인 claim 의 llm_value (없으면 None)."""
    for c in o.get("claims", []):
        s = c.get(slot)
        if isinstance(s, dict) and str(s.get("raw")) == raw:
            return s.get("llm_value")
    return None


def main() -> None:
    gold = load_gold()
    outs = load_output()

    # ── 모드 A: rule-only on gold.raw ───────────────────────────────────────
    a_rows = []
    a_tally = {s: [0, 0] for s in SLOTS}  # [correct, total]
    for g in gold:
        base = g.get("base", "")
        for s in SLOTS:
            gs = g.get(s)
            if not gs:
                continue
            match = gs.get("match", "exact")
            pred = normalize(s, gs["raw"], base)
            ok = is_match(gs["expected"], pred, match)
            a_tally[s][0] += int(ok)
            a_tally[s][1] += 1
            if not ok:
                a_rows.append({
                    "id": g["id"], "slot": s, "raw": gs["raw"],
                    "expected": gs["expected"], "pred": pred,
                    "kind": gs.get("kind"), "match": match,
                })

    # ── 모드 B: gold vs 기존 output.jsonl (id+슬롯 raw 매칭) ─────────────────
    b_tally = {s: {"matched": 0, "correct": 0, "total": 0} for s in SLOTS}
    for g in gold:
        o = outs.get(g["id"])
        for s in SLOTS:
            gs = g.get(s)
            if not gs:
                continue
            b_tally[s]["total"] += 1
            if not o:
                continue
            pred = out_raw_value(o, s, gs["raw"])
            if pred is None and gs["raw"] not in [
                str((c.get(s) or {}).get("raw")) for c in o.get("claims", [])
            ]:
                continue  # raw 미추출 = 매칭 실패(stage-2 갭)
            b_tally[s]["matched"] += 1
            if is_match(gs["expected"], pred, gs.get("match", "exact")):
                b_tally[s]["correct"] += 1

    # ── 집계 ────────────────────────────────────────────────────────────────
    def acc(c, t):
        return round(c / t, 3) if t else None

    a_summary = {s: {"correct": a_tally[s][0], "total": a_tally[s][1],
                     "acc": acc(*a_tally[s])} for s in SLOTS}
    a_c = sum(a_tally[s][0] for s in SLOTS)
    a_t = sum(a_tally[s][1] for s in SLOTS)
    a_summary["overall"] = {"correct": a_c, "total": a_t, "acc": acc(a_c, a_t)}

    result = {
        "gold": str(GOLD), "output": str(OUTPUT), "n_gold": len(gold),
        "mode_A_rule_only_vs_gold": a_summary,
        "mode_A_mismatches": a_rows,
        "mode_B_existing_output_vs_gold": b_tally,
    }
    out_path = Path(__file__).with_name(Path(__file__).stem + "_result.json")
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 출력 ────────────────────────────────────────────────────────────────
    print("=== 모드 A: 현재 룰(rule-only) vs gold ===")
    for s in SLOTS:
        d = a_summary[s]
        print(f"  {s:22s} {d['correct']:3d}/{d['total']:3d}  acc={d['acc']}")
    o = a_summary["overall"]
    print(f"  {'OVERALL':22s} {o['correct']:3d}/{o['total']:3d}  acc={o['acc']}")
    print(f"  오답 {len(a_rows)}건 (상세 _result.json)")

    print("\n=== 모드 B: 기존 output.jsonl vs gold (id+슬롯 raw 매칭) ===")
    print("  (matched=raw 추출됨 / total=gold 슬롯 수 / correct=정규화 일치)")
    for s in SLOTS:
        d = b_tally[s]
        ma = acc(d["correct"], d["matched"])
        print(f"  {s:22s} matched {d['matched']:3d}/{d['total']:3d}"
              f"  normalize-acc(매칭분) {d['correct']:3d}/{d['matched']:3d}={ma}")
    print("  ※ compare_period_value 매칭 저조 = stage-2 비교시점 미추출 갭(=normalize 책임 아님)")


if __name__ == "__main__":
    main()
