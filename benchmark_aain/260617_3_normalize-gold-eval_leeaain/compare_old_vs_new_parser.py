"""옛 파서(9a0f039^=2549e8d) vs 현재 파서 — 동일 스코어러·동일 gold·rule-only 비교.

신규 스코어러 모드A 로직을 그대로 쓰되, 옛 _parse_value(async, LLM 포함)는
parse_korean_numeral/parse_number 를 rule-only 래퍼로 패치해 'rule 능력'만 잰다.
현재 _parse_value(sync rule-only)는 패치 무관. 두 코드베이스에서 같은 파일을 실행한다.

실행:
  현재:  cd <main> && uv run python benchmark/260617_3_normalize-gold-eval_leeaain/compare_old_vs_new_parser.py
  옛:    cp 이 파일 -> /tmp/fnd_old_parser/ && cd /tmp/fnd_old_parser && uv run python compare_old_vs_new_parser.py
"""
from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path

# gold 는 항상 메인 저장소 절대경로(양쪽 동일 입력 보장)
GOLD = Path("/Users/leeaain/project/pinokio-x/fake_news_detect/benchmark/data/3_normalize_claim_100_gold.jsonl")
SLOTS = ["value", "period_value", "compare_period_value"]

import src.modules.normalize_claim as nm  # noqa: E402

# ── rule-only 강제: 옛 _parse_value 의 LLM 진입(parse_korean_numeral/parse_number)을
#    rule-only 래퍼로 교체. 신규엔 이 심볼이 없으니 no-op. ─────────────────────────
try:
    import src.modules.parse_korean_number as pk
    if hasattr(nm, "parse_korean_numeral"):
        async def _kn(raw):  # rule-only
            return pk._parse_korean_numeral_rule(raw)
        nm.parse_korean_numeral = _kn
    if hasattr(nm, "parse_number"):
        async def _n(raw):   # rule-only
            return pk._parse_number_rule(raw)
        nm.parse_number = _n
except Exception as e:  # noqa
    print("patch warn:", e)


def parse_value(raw):
    r = nm._parse_value(raw)
    if inspect.isawaitable(r):
        r = asyncio.run(r)
    return r


def normalize(slot, raw, base):
    if slot == "value":
        return parse_value(raw)
    return nm._normalize_period(raw, base)


def is_match(expected, pred, match):
    if pred is None:
        return False
    e, p = str(expected).strip(), str(pred).strip()
    if match == "num":
        try:
            return abs(float(e) - float(p)) < 1e-9
        except ValueError:
            return e == p
    return e == p


def main():
    gold = [json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("//")]
    tally = {s: [0, 0] for s in SLOTS}
    mism = []
    for g in gold:
        base = g.get("base", "")
        for s in SLOTS:
            gs = g.get(s)
            if not gs:
                continue
            pred = normalize(s, gs["raw"], base)
            ok = is_match(gs["expected"], pred, gs.get("match", "exact"))
            tally[s][0] += int(ok)
            tally[s][1] += 1
            if not ok:
                mism.append({"id": g["id"], "slot": s, "raw": gs["raw"],
                             "expected": gs["expected"], "pred": pred})

    c = sum(tally[s][0] for s in SLOTS)
    t = sum(tally[s][1] for s in SLOTS)
    print(f"loaded normalize_claim from: {nm.__file__}")
    for s in SLOTS:
        cc, tt = tally[s]
        print(f"  {s:22s} {cc:3d}/{tt:3d}  acc={cc/tt:.3f}" if tt else f"  {s}: 0")
    print(f"  {'OVERALL':22s} {c:3d}/{t:3d}  acc={c/t:.3f}")
    # 결과를 JSON 으로도 (양쪽 비교용)
    out = {"loaded_file": nm.__file__,
           "per_slot": {s: {"correct": tally[s][0], "total": tally[s][1]} for s in SLOTS},
           "overall": {"correct": c, "total": t, "acc": round(c / t, 4)},
           "mismatches": mism}
    print("JSON_RESULT_BEGIN")
    print(json.dumps(out, ensure_ascii=False))
    print("JSON_RESULT_END")


if __name__ == "__main__":
    main()
