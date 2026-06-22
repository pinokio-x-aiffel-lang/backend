"""단위 표기 정규화 개선 전/후 — after6 캡처에 7단계(calculate_metric) 재실행.

unknown_unit 으로 NEI 빠지던 케이스가 수정 후 NEI 탈출하는지 측정.
결정적(LLM·KOSIS 미호출)이라 캡처만으로 재현.
"""
import asyncio
import json
import re

from src.modules.calculate_metric import calculate_metric
from src.schemas.runtime import MasterSchema

CAPTURE = "benchmark_aain/data/260622_capture_v2_snapshots.jsonl"
TARGET_ROWS = [32, 37, 64, 95, 198, 211]  # unknown_unit NEI 케이스


def _note_cat(note: str) -> str:
    if "unknown_unit" in note:
        m = re.search(r"claim=(.+?) kosis=(.+)$", note)
        pair = f"{m.group(1)}↔{m.group(2)}" if m else ""
        return f"NEI(unknown_unit) {pair}"
    if "incompatible" in note:
        return "NEI(incompatible)"
    return ""


async def main() -> None:
    rows = [json.loads(l) for l in open(CAPTURE) if l.strip()]
    unknown_unit_cases = []  # (row_id, claim_id, verdict, pair)

    for r in rows:
        a6 = r["snapshots"].get("after6")
        if not a6:
            continue
        ms = MasterSchema.model_validate(a6)
        ms.verifications = None  # 7단계가 다시 만들도록 초기화
        await calculate_metric(ms)
        for cr in ms.verifications.claim_results:
            m = cr.metric
            note = (m.note or "") if m else ""
            verdict = m.verdict.value if (m and m.verdict) else cr.verdict
            if "unknown_unit" in note:
                mm = re.search(r"claim=(.+?) kosis=(.+)$", note)
                pair = f"{mm.group(1)}↔{mm.group(2)}" if mm else note[:40]
                unknown_unit_cases.append((r["row_id"], cr.claim_id, verdict, pair))

    print(f"TOTAL_UNKNOWN_UNIT_NEI={len(unknown_unit_cases)}")
    for rid, cid, v, pair in sorted(unknown_unit_cases):
        is_nei = "NEI" if v in ("N", "NOT_ENOUGH_INFO") else "탈출"
        print(f"ROW {rid:>4} {cid} | verdict={v} | {is_nei} | {pair}")


asyncio.run(main())
