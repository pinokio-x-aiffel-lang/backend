"""단위 표기 정규화/가정비교 개선 전/후 — after6 캡처에 7단계(calculate_metric) 재실행.

per-claim verdict 를 JSON 으로 덤프해 before/after 1:1 비교(회귀 측정)에 쓴다.
사용: uv run python benchmark_aain/_unit_norm_eval.py <out.json>
결정적(LLM·KOSIS 미호출)이라 캡처만으로 재현.
"""
import asyncio
import json
import re
import sys
import collections

from src.modules.calculate_metric import calculate_metric
from src.schemas.runtime import MasterSchema

CAPTURE = "benchmark_aain/data/260622_capture_v2_snapshots.jsonl"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/unit_eval.json"


async def main() -> None:
    rows = [json.loads(l) for l in open(CAPTURE) if l.strip()]
    per_claim = {}                    # "row:claim" -> {verdict, note, gold}
    dist = collections.Counter()
    unit_cases = []                   # 단위 관련 NEI/탈출 케이스

    for r in rows:
        a6 = r["snapshots"].get("after6")
        if not a6:
            continue
        ms = MasterSchema.model_validate(a6)
        ms.verifications = None
        await calculate_metric(ms)
        for cr in ms.verifications.claim_results:
            m = cr.metric
            note = (m.note or "") if m else ""
            v = (m.verdict.value if (m and m.verdict) else cr.verdict)
            key = f"{r['row_id']}:{cr.claim_id}"
            per_claim[key] = {"verdict": v, "note": note, "gold": r.get("label")}
            dist[v] += 1
            if any(t in note for t in ("unknown_unit", "단위 가정", "스케일 근사", "단위 미해소")):
                mm = re.search(r"claim=(.+?) kosis=(.+?)(?:\)|$| →|;)", note)
                pair = f"{mm.group(1)}↔{mm.group(2)}" if mm else ""
                unit_cases.append((r["row_id"], cr.claim_id, v, r.get("label"), pair, note[:90]))

    json.dump(per_claim, open(OUT, "w"), ensure_ascii=False, indent=0)
    print(f"DIST {dict(dist)}")
    print(f"UNIT_RELATED_CASES={len(unit_cases)}")
    for rid, cid, v, gold, pair, note in sorted(unit_cases):
        nei = "NEI" if v in ("N", "NOT_ENOUGH_INFO") else "탈출"
        print(f"ROW {rid:>4} {cid} | verdict={v}({nei}) gold={gold} | {pair} | {note}")


asyncio.run(main())
