"""2~6_from_labeled_true_source.jsonl → 2→5 실행 + 5단계 gold 값 채점.

각 record.claim 을 파이프라인 1→5 단계(load_article→extract→normalize→retrieve→fetch)로
흘려보내고, stage5 가 가져온 evidences(KOSIS 공식값)를 record.gold(원래 통계표 수치)와
대조해 gold figure recall(값 / 값+시점)을 집계한다.

  - 채점 대상: [5] fetch_kosis_data 가 올바른 셀 값을 재현했는가.
  - [1]~[4]는 흘려보내기용 도구(검증 대상 아님). subject/population 은 [2]가 생성.
  - gold 가 범위(period 'A~B', value 리스트)/None 인 엔트리는 단일셀 대조 불가라 제외.

실행:  uv run x python benchmark/run_2to5_gold_eval.py [--limit N] [--concurrency K]
결과:  tests/results/260615_2-5_gold-figure-recall_leeaain.json (+ .md)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path

from src.modules.extract_statistical_claims import extract_statistical_claims
from src.modules.fetch_kosis_data import fetch_kosis_data
from src.modules.load_article import load_article
from src.modules.normalize_claim import normalize_claim
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.schemas.runtime import MasterSchema

DATA = Path("benchmark/data/2~6_from_labeled_true_source.jsonl")
OUTJSON = Path("tests/results/260615_2-5_gold-figure-recall_leeaain.json")
OUTMD = Path("tests/results/260615_2-5_gold-figure-recall_leeaain.md")
STEPS = [
    ("1", load_article),
    ("2", extract_statistical_claims),
    ("3", normalize_claim),
    ("4", retrieve_kosis_candidates),
    ("5", fetch_kosis_data),
]


def canon_period(p) -> str | None:
    """gold(YYYY-MM / YYYY / YYYY-Qn) · evidence(KOSIS PRD_DE) → 비교용 정규형. 범위는 None."""
    p = str(p or "").strip()
    if "~" in p:
        return None
    m = re.match(r"^(\d{4})-Q([1-4])$", p)
    if m:
        return f"{m.group(1)}{int(m.group(2)):02d}"
    m = re.match(r"^(\d{4})-(\d{2})$", p)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    if re.match(r"^\d{4}$", p):
        return p
    d = re.sub(r"\D", "", p)
    return d or None


def vmatch(e, g, rtol=0.01, atol=0.5) -> bool:
    """값 일치(상대 1% 또는 절대 0.5 이내). 둘 다 KOSIS 단위(천명 등)라 직접 비교."""
    try:
        e, g = float(e), float(g)
    except (TypeError, ValueError):
        return False
    return abs(e - g) <= max(atol, rtol * abs(g))


# 증감/변화 gold 는 [5] 절대값 조회로 재현 불가(그룹연산 미배선) → 분리 집계.
_DELTA_KW = ("증감", "증가", "감소", "전년", "전월", "대비")


def gold_type(item: str | None) -> str:
    return "delta" if any(k in (item or "") for k in _DELTA_KW) else "absolute"


async def _run_one(rec: dict) -> dict:
    ms = MasterSchema(content=rec["claim"])
    err = None
    t0 = time.perf_counter()
    for _no, fn in STEPS:
        try:
            await fn(ms)
        except Exception as exc:
            err = f"{fn.__name__}: {exc}"
            break
    dur = time.perf_counter() - t0

    # 한 문장에서 [2]가 여러 claim 을 뽑을 수 있으니 evidences 를 풀링
    evs = [
        {"period": ev.period, "value": ev.value, "unit": ev.unit,
         "item_id": ev.kosis_item_id, "tbl": ev.kosis_tbl_id, "tbl_nm": ev.table_name}
        for an in ms.analysis for ev in (an.evidences or [])
    ]
    subjects = [c.subject for c in ms.claims]

    gold_results = []
    for g in rec.get("gold", []):
        gv, gp = g.get("value"), g.get("period")
        if gv is None or isinstance(gv, list):          # 범위/항목없음 → 단일셀 대조 불가
            gold_results.append({"gold": g, "kind": "range_or_none", "value_hit": None, "vp_hit": None})
            continue
        vhit = any(vmatch(e["value"], gv) for e in evs)
        matched = next(
            (e for e in evs if vmatch(e["value"], gv) and canon_period(e["period"]) == canon_period(gp)),
            next((e for e in evs if vmatch(e["value"], gv)), None),
        )
        vphit = matched is not None and canon_period(matched["period"]) == canon_period(gp)
        gold_results.append({"gold": g, "kind": "single", "type": gold_type(g.get("item")),
                             "value_hit": vhit, "vp_hit": vphit, "matched_ev": matched})

    return {
        "id": rec["id"], "claim": rec["claim"][:70], "label": rec.get("label"),
        "ok": err is None, "error": err, "duration_s": round(dur, 2),
        "n_claims": len(ms.claims), "subjects": subjects, "n_evidences": len(evs),
        "evidences": evs, "gold_results": gold_results,
    }


def _read(path: Path, limit: int) -> list[dict]:
    rows = [json.loads(s) for ln in path.read_text(encoding="utf-8").splitlines()
            if (s := ln.strip()).startswith("{")]
    return rows[:limit] if limit else rows


async def _run_all(rows: list[dict], conc: int) -> list[dict]:
    sem = asyncio.Semaphore(conc)
    total = len(rows)
    done = [0]

    async def guarded(rec):
        async with sem:
            r = await _run_one(rec)
            done[0] += 1
            ab = [x for x in r["gold_results"] if x.get("type") == "absolute"]
            vh = sum(1 for x in ab if x["value_hit"])
            tag = "OK " if r["ok"] else "ERR"
            print(f"[{done[0]:>3}/{total}] {tag} {r['duration_s']:5.1f}s ev={r['n_evidences']} "
                  f"absHit={vh}/{len(ab)} | {r['claim'][:34]}…")
            return r

    return sorted(await asyncio.gather(*(guarded(x) for x in rows)), key=lambda r: r["id"])


def _summary(items: list[dict]) -> dict:
    single = [g for it in items for g in it["gold_results"] if g["kind"] == "single"]
    excluded = [g for it in items for g in it["gold_results"] if g["kind"] != "single"]
    absol = [g for g in single if g["type"] == "absolute"]      # [5]가 재현 가능한 절대값형
    delta = [g for g in single if g["type"] == "delta"]          # 증감형(미배선) → 참고용
    a_vh = sum(1 for g in absol if g["value_hit"])
    a_vph = sum(1 for g in absol if g["vp_hit"])
    return {
        "records": len(items),
        "ok": sum(1 for it in items if it["ok"]),
        "fail": sum(1 for it in items if not it["ok"]),
        "records_with_evidence": sum(1 for it in items if it["n_evidences"] > 0),
        "total_claims_extracted": sum(it["n_claims"] for it in items),
        "total_evidences": sum(it["n_evidences"] for it in items),
        "gold_single": len(single),
        "gold_absolute": len(absol),
        "gold_delta_unwired": len(delta),
        "gold_range_or_none_excluded": len(excluded),
        # 주지표: 절대값형 gold 에 대한 [5] 재현율
        "abs_value_recall": round(a_vh / len(absol), 4) if absol else 0.0,
        "abs_value_period_recall": round(a_vph / len(absol), 4) if absol else 0.0,
        "abs_value_hits": a_vh, "abs_value_period_hits": a_vph,
        # 참고: 증감형은 절대조회로 재현 불가(거의 0 예상)
        "delta_value_hits": sum(1 for g in delta if g["value_hit"]),
    }


def _md(s: dict) -> str:
    L = [f"# {OUTMD.stem}", ""]
    L += ["### 1. 테스트 목적",
          "`2~6_from_labeled_true_source.jsonl`(123건, 전부 label=True)의 각 claim을 파이프라인 "
          "[1]~[5]로 흘려보내고, **[5] fetch_kosis_data가 가져온 값이 gold(원래 통계표 수치)를 "
          "재현하는지**(gold figure recall)를 채점한다.", ""]
    L += ["### 2. 검증 대상 모듈", "- src/modules/fetch_kosis_data.py — [5] KOSIS 셀 값 조회", ""]
    L += ["### 3. 도구로만 쓰인 모듈 (검증 대상 아님)",
          "- [1] load_article · [2] extract_statistical_claims · [3] normalize_claim · "
          "[4] retrieve_kosis_candidates (흘려보내기용; subject/population은 [2]가 생성)", ""]
    L += ["### 4. 테스트 일자 / 작성자", "- 일자: 2026-06-15", "- 작성자: leeaain", ""]
    L += [f"### 5. 결과  (원자료: {OUTJSON.name})",
          f"- 레코드: {s['records']} (성공 {s['ok']} / 실패 {s['fail']})",
          f"- evidence 1개+ 확보 레코드: {s['records_with_evidence']}/{s['records']}",
          f"- 추출 claim 총 {s['total_claims_extracted']} · evidence 총 {s['total_evidences']}",
          "",
          "**gold figure 분류**: "
          f"단일값 {s['gold_single']} = 절대값형 {s['gold_absolute']} + 증감형(미배선) "
          f"{s['gold_delta_unwired']} · 제외(범위/항목없음) {s['gold_range_or_none_excluded']}",
          "",
          f"- **[5] 절대값 재현율 (값): {s['abs_value_recall']:.3f}** "
          f"({s['abs_value_hits']}/{s['gold_absolute']})  ← 주지표",
          f"- [5] 절대값 재현율 (값+시점): {s['abs_value_period_recall']:.3f} "
          f"({s['abs_value_period_hits']}/{s['gold_absolute']})",
          f"- (참고) 증감형 gold 적중: {s['delta_value_hits']}/{s['gold_delta_unwired']} "
          "— 절대조회로는 재현 불가(그룹연산 미배선, 거의 0이 정상)", ""]
    L += ["### 6. 한계 / 범위 밖",
          "- gold tbl_id 없음 → [4] 표 recall은 직접 채점 불가(값 일치로 간접).",
          "- 값 정규화([3] value)·subject/population([2]) 정답 없음 → 본 채점은 [5] 값 한정.",
          "- **증감형 gold**(증감/전년동월비 등)는 [5] 절대조회로 재현 불가 → 별도 집계, 주지표서 제외.",
          "- 범위·비교형 gold(period 'A~B'/다중값)는 단일셀 대조 불가라 제외.",
          "- 발행일 미상 → [1]의 더미 base(2025-04)로 상대시점 정규화(일부 오차 가능).",
          "- 관측: population 미추출 시 [5]가 전국(계) 대신 시도값을 매칭하는 경향(예 id1: 5116≠28589).",
          "- label이 전부 True → 가짜 탐지(7~9)는 범위 밖."]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=6)
    args = ap.parse_args()

    rows = _read(DATA, args.limit)
    print(f"2→5 실행 + gold 채점 시작 — {len(rows)}건, 동시 {args.concurrency}\n")
    items = asyncio.run(_run_all(rows, args.concurrency))
    summary = _summary(items)

    OUTJSON.parent.mkdir(parents=True, exist_ok=True)
    OUTJSON.write_text(json.dumps(
        {"source": str(DATA), "stages": "1-5(채점=5)", "summary": summary, "records": items},
        ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    OUTMD.write_text(_md(summary), encoding="utf-8")

    print(f"\n{json.dumps(summary, ensure_ascii=False)}")
    print(f"저장: {OUTJSON}\n      {OUTMD}")


if __name__ == "__main__":
    main()
