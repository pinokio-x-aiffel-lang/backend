"""38 T행에 현재 retrieve(stage4) 실행 → L1 대분류명·L2 조사명·최종 후보 tbl_id 기록.

_llm_pick 을 몽키패치(모니터링)해 트리에서 LLM 이 고른 노드명을 잡는다(production 무변경).
원문 문장·라벨러 정답표(primary + 값-일치 후보집합)도 함께 넣어 비교 가능하게.

출력: benchmark_aain/data/260624_agent_system_4~5_table_query.json
실행: uv run x python benchmark_aain/build_agent_45_query.py
"""
from __future__ import annotations

import asyncio
import collections
import json
from pathlib import Path

from src.schemas.runtime import MasterSchema
from src.modules import retrieve_kosis_candidates as R

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "benchmark/data/ssot/260624_origin_sentence_gold_tblid.json"
GTC = ROOT / "benchmark_aain/data/gold_t_confirmed.jsonl"
CAP = ROOT / "benchmark_aain/data/260624_capture_v2_e75a7b2.jsonl"
OUT = ROOT / "benchmark_aain/data/260624_agent_system_4~5_table_query.json"


def loadl(p):
    return [json.loads(s) for ln in Path(p).read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


# 38 = gold_tbl_id 채워진 T행
gold = {x["row_id"]: x for x in json.load(open(GOLD)) if x.get("gold_tbl_id")}
# 값-일치 표 후보집합 (ambiguous 대비)
cand_sets = collections.defaultdict(set)
for r in loadl(GTC):
    for m in (r.get("matches") or []):
        cand_sets[r["row_id"]].add(m["tbl_id"])
cap = {r["row_id"]: r for r in loadl(CAP)}
sent = {}
for rid, r in cap.items():
    for c in (r["snapshots"].get("after2", {}).get("claims") or []):
        sent[(rid, c["claim_id"])] = c.get("sentence")

# _llm_pick 몽키패치 — 선택 노드명 기록(claim_id 키)
rec = collections.defaultdict(list)
_orig = R._llm_pick
async def _patched(claim, keyword, period, breadcrumb, options):
    idxs = await _orig(claim, keyword, period, breadcrumb, options)
    rec[claim.claim_id].append((breadcrumb, [options[i] for i in idxs if 0 <= i < len(options)]))
    return idxs
R._llm_pick = _patched


async def run_row(rid):
    r = cap.get(rid)
    if not r or not r["snapshots"].get("after4"):
        return None
    ms = MasterSchema.model_validate(r["snapshots"]["after4"])
    ms.analysis = []
    rec.clear()
    await R.retrieve_kosis_candidates(ms)
    primary = gold[rid]["gold_tbl_id"]
    cands = sorted(cand_sets.get(rid, {primary}))
    claims = []
    for a in ms.analysis:
        cid = a.claim_id
        picks = rec.get(cid, [])
        l1 = next(([n for n in names] for bc, names in picks if "최상위" in bc), [])
        l2 = next(([n for n in names] for bc, names in picks if bc.startswith("상위")), [])
        final = [c.tbl_id for c in (a.candidates or [])]
        claims.append({
            "claim_id": cid,
            "sentence": sent.get((rid, cid)),
            "L1_chosen_majors": l1,
            "L2_chosen_surveys": l2,
            "final_candidate_tbl_ids": final,
            "gold_primary_in_candidates": primary in final,
            "any_gold_candidate_in_candidates": bool(set(cands) & set(final)),
        })
    return {
        "row_id": rid,
        "labeler_keyword": gold[rid].get("subject"),
        "gold_tbl_id": primary,
        "gold_tbl_candidates": cands,
        "claims": claims,
    }


async def main():
    out = []
    for rid in sorted(gold):
        res = await run_row(rid)
        if res:
            out.append(res)
            print(f"  row{rid} done ({len(res['claims'])} claims)", flush=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    tot = sum(len(x["claims"]) for x in out)
    hit_p = sum(1 for x in out for c in x["claims"] if c["gold_primary_in_candidates"])
    hit_a = sum(1 for x in out for c in x["claims"] if c["any_gold_candidate_in_candidates"])
    print(f"\n저장: {OUT}")
    print(f"행 {len(out)} | claim {tot} | primary 후보적중 {hit_p}/{tot} | 값-일치표 적중 {hit_a}/{tot}")


if __name__ == "__main__":
    asyncio.run(main())
