"""from_origin_100_TRUE 문장들을 1~5단계에 통과 → claim별 KOSIS 조회 결과 수집.

[1]load_article [2]extract [3]normalize [4]retrieve_kosis_candidates [5]fetch_kosis_data
claim별: 값 발견(TRUE/FALSE) / 후보 통계표 / 조회에 쓴 메타(itmId·objL·period) /
실제 표 메타(items·axes) / 단계 미통과 사유 를 JSON 으로 저장.

    uv run x python tests/run_pipeline_1to5.py
"""
from __future__ import annotations

import asyncio
import inspect
import json
import time
from pathlib import Path

from src.modules.extract_statistical_claims import extract_statistical_claims
from src.modules.fetch_kosis_data import fetch_kosis_data
from src.modules.load_article import load_article
from src.modules.normalize_claim import normalize_claim
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.schemas.runtime import MasterSchema

SRC = Path("benchmark/data/from_origin_100_TRUE(human_check).txt")
OUT = Path("tests/results/260612_1-5_pipeline_leeaain.json")
sem = asyncio.Semaphore(2)

STAGES = [("1_load", load_article), ("2_extract", extract_statistical_claims),
          ("3_normalize", normalize_claim), ("4_retrieve", retrieve_kosis_candidates),
          ("5_fetch", fetch_kosis_data)]


async def _call(fn, ms):
    r = fn(ms)
    if inspect.isawaitable(r):
        await r


def _enum(v):
    return getattr(v, "value", v)


async def run_sentence(n, sent):
    rec = {"n": n, "sentence": sent, "stage_fail": None, "claims": []}
    ms = MasterSchema(content=sent)
    async with sem:
        for sname, fn in STAGES:
            try:
                await _call(fn, ms)
            except Exception as e:  # noqa: BLE001
                rec["stage_fail"] = f"{sname}: {type(e).__name__} {str(e)[:120]}"
                return rec
            if sname == "2_extract" and not ms.claims:
                rec["stage_fail"] = "2_extract: claim 미추출"
                return rec
    # claim별 결과 (analysis 는 claims 순서와 정렬)
    for i, c in enumerate(ms.claims):
        an = ms.analysis[i] if i < len(ms.analysis) else None
        ev = next((e for e in (an.evidences if an else []) if e.value is not None), None)
        atts = [{
            "tbl_nm": a.tbl_nm, "itm_id": a.itm_id, "matched": a.matched,
            "value": a.value, "population_fallback": a.population_fallback,
            "items": a.items[:6], "axes": {k: v[:4] for k, v in list(a.axes.items())[:3]},
            "error": a.error,
        } for a in (an.cell_attempts if an else [])]
        hits = an.kosis_search.hits if an else 0
        block = None
        if hits == 0:
            block = "4_retrieve: 후보표 0"
        elif ev is None:
            err = next((a["error"] for a in atts if a["error"]), None)
            block = f"5_fetch: 값 미발견 ({err or '좌표/시점 미해소'})"
        rec["claims"].append({
            "subject": c.subject, "value_raw": c.value.raw, "value_norm": c.value.llm_value,
            "period_type": _enum(c.period_type), "period": c.period_value.llm_value or c.period_value.raw,
            "population": c.population,
            "found": ev is not None,
            "candidates": [cd.tbl_nm for cd in (an.candidates if an else [])][:5],
            "evidence": (None if ev is None else {
                "value": ev.value, "table_name": ev.table_name, "tbl_id": ev.kosis_tbl_id,
                "itm_id": ev.kosis_item_id, "classification": ev.classification, "period": ev.period,
            }),
            "attempts": atts,
            "stage_block": block,
        })
    return rec


async def main():
    sents = [ln.strip() for ln in SRC.read_text(encoding="utf-8").splitlines() if ln.strip()]
    t0 = time.perf_counter()
    out = []
    done = 0
    tasks = [run_sentence(i + 1, s) for i, s in enumerate(sents)]
    for fut in asyncio.as_completed(tasks):
        out.append(await fut)
        done += 1
        if done % 10 == 0:
            print(f"  진행 {done}/{len(sents)}  ({time.perf_counter()-t0:.0f}s)", flush=True)
    out.sort(key=lambda r: r["n"])
    dur = time.perf_counter() - t0

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"input": str(SRC), "n_sentences": len(sents),
                               "duration_s": round(dur, 1), "results": out},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    n_claims = sum(len(r["claims"]) for r in out)
    n_true = sum(1 for r in out for c in r["claims"] if c["found"])
    n_sfail = sum(1 for r in out if r["stage_fail"])
    print(f"\n문장 {len(sents)} | claim {n_claims} | 값발견(TRUE) {n_true} | 단계미통과 문장 {n_sfail} | {dur:.0f}s")
    print(f"저장: {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
