"""38 T행에 현재 retrieve 실행 → KOSIS 에 '실제로 보낸 키워드'(statisticsSearch.do searchNm)만 기록.

트리(statisticsList.do)는 searchNm 안 보냄 → 제외. search_tables_many 에 들어간 변형 목록만 캡처.
claim 단위 정확 귀속 위해 단일-claim MasterSchema 로 순차 실행.

출력: benchmark_aain/data/260624_agent_system_4~5_table_query.jsonl (덮어씀)
실행: uv run x python benchmark_aain/capture_sent_keywords.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.schemas.runtime import MasterSchema
from src.modules import retrieve_kosis_candidates as R

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "benchmark/data/ssot/260624_origin_sentence_gold_tblid.json"
CAP = ROOT / "benchmark_aain/data/260624_capture_v2_e75a7b2.jsonl"
OUT = ROOT / "benchmark_aain/data/260624_agent_system_4~5_table_query.jsonl"


def loadl(p):
    return [json.loads(s) for ln in Path(p).read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


rows38 = {x["row_id"] for x in json.load(open(GOLD)) if x.get("gold_tbl_id")}
cap = {r["row_id"]: r for r in loadl(CAP)}
sent_txt = {}
for rid, r in cap.items():
    for c in (r["snapshots"].get("after2", {}).get("claims") or []):
        sent_txt[(rid, c["claim_id"])] = c.get("sentence")

# search_tables_many 모니터링 — 실제로 보낸 키워드 목록 기록
_sent = []
_orig = R.search_tables_many
def _patched(keywords, *a, **k):
    _sent.append(list(keywords))
    return _orig(keywords, *a, **k)
R.search_tables_many = _patched


async def run_claim(ms_full, claim):
    ms = ms_full.model_copy(deep=True)
    ms.claims = [claim]
    ms.analysis = []
    _sent.clear()
    await R.retrieve_kosis_candidates(ms)
    kws = [k for lst in _sent for k in lst]  # 실제 보낸 키워드 평탄화
    final = [c.tbl_id for c in (ms.analysis[0].candidates or [])] if ms.analysis else []
    return {"kosis_search_keywords": kws, "final_tbl_ids": final}


async def main():
    out = []
    for rid in sorted(rows38):
        r = cap.get(rid)
        if not r or not r["snapshots"].get("after4"):
            continue
        ms_full = MasterSchema.model_validate(r["snapshots"]["after4"])
        for claim in ms_full.claims:
            rec = await run_claim(ms_full, claim)
            out.append({
                "row_id": rid, "claim_id": claim.claim_id,
                "sentence": sent_txt.get((rid, claim.claim_id)),
                "kosis_search_keywords": rec["kosis_search_keywords"],
                "final_tbl_ids": rec["final_tbl_ids"],
            })
        print(f"  row{rid} done ({len(ms_full.claims)} claims)", flush=True)
    with OUT.open("w", encoding="utf-8") as f:
        for rec in out:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tot_kw = sum(len(x["kosis_search_keywords"]) for x in out)
    print(f"\n저장: {OUT}")
    print(f"라인(claim) {len(out)} | 평균 보낸 키워드 {tot_kw/len(out):.1f}/claim")


if __name__ == "__main__":
    asyncio.run(main())
