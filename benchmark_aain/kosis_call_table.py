"""claim별 KOSIS 호출수 집계 테이블 — 캡처의 ClaimAnalysis.kosis_calls 사용.

after4.kosis_calls = [4] retrieve 호출수, after6.kosis_calls = [4]+[5] 누적
→ stage5 = after6 - after4. logical GET 기준(재시도 미포함).

실행: uv run python benchmark_aain/kosis_call_table.py <capture.jsonl>
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

CAP = Path(sys.argv[1])


def load(p):
    return [json.loads(s) for ln in Path(p).read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def main():
    cap = load(CAP)
    rows = []  # (row_id, claim_id, subject, s4, s5, total)
    for r in cap:
        rid = r["row_id"]
        a4 = {a["claim_id"]: a for a in (r["snapshots"].get("after4", {}).get("analysis") or [])}
        a6 = {a["claim_id"]: a for a in (r["snapshots"].get("after6", {}).get("analysis") or [])}
        claims6 = {c["claim_id"]: c for c in (r["snapshots"].get("after6", {}).get("claims") or [])}
        for cid, a in a6.items():
            s4 = (a4.get(cid) or {}).get("kosis_calls", 0)
            total = a.get("kosis_calls", 0)
            rows.append((rid, cid, (claims6.get(cid) or {}).get("subject", ""),
                         s4, max(0, total - s4), total))

    totals = [t for *_, t in rows]
    s4s = [s4 for *_, s4, _, _ in rows]
    s5s = [s5 for *_, s5, _ in rows]
    n = len(rows)

    print(f"=== claim별 KOSIS 호출수 — capture {CAP.name} ({n} claims) ===\n")
    print("| 구간 | 합계 | 평균/claim | 중앙값 | 최소 | 최대 |")
    print("|---|---|---|---|---|---|")
    for label, xs in [("[4] retrieve", s4s), ("[5] fetch", s5s), ("전체", totals)]:
        print(f"| {label} | {sum(xs):,} | {statistics.mean(xs):.1f} | "
              f"{statistics.median(xs):.0f} | {min(xs)} | {max(xs)} |")
    print(f"\n전체 KOSIS logical GET = **{sum(totals):,}회** ({n} claims, 213 기사)")
    print(f"(rate limit 1000/min 기준 이론 최소 ~{sum(totals)/1000:.1f}분)")

    # 호출수 상위 10 claim
    print("\n### 호출 많은 claim Top 10")
    print("| row | claim | subject | [4] | [5] | 합계 |")
    print("|---|---|---|---|---|---|")
    for rid, cid, subj, s4, s5, tot in sorted(rows, key=lambda x: -x[5])[:10]:
        print(f"| {rid} | {cid} | {subj[:20]} | {s4} | {s5} | {tot} |")

    # 전체 per-claim 저장
    out = CAP.parent / f"kosis_calls_{CAP.stem}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for rid, cid, subj, s4, s5, tot in rows:
            f.write(json.dumps({"row_id": rid, "claim_id": cid, "subject": subj,
                                "stage4_calls": s4, "stage5_calls": s5, "total_calls": tot},
                               ensure_ascii=False) + "\n")
    print(f"\n전체 per-claim → {out}")


if __name__ == "__main__":
    main()
