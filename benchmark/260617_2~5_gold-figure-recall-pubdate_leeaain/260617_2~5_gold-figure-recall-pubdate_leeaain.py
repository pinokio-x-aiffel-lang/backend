"""2~5 gold-figure-recall — 발행일(published_at) 더미 vs 실제추정 통제 비교.

기존(260615) 테스트는 [1] load_article 이 published_at 을 더미 "2025-04" 로 박아
[3] normalize_claim 의 상대시점 base 로 썼다. 본 테스트는 발행일을 '보도시점 추정'으로
채웠을 때 [5] gold figure recall 이 얼마나 바뀌는지를 **통제 비교**한다.

설계(노이즈 제거):
  - record 당 [1] load_article + [2] extract_statistical_claims 를 **한 번만** 실행
    → 두 조건이 동일한 추출 claim 을 공유(추출 LLM 비결정성 제거).
  - 그 뒤 MasterSchema 를 deep-copy 해 두 갈래로 [3][4][5] 실행:
      A(dummy)   : published_at = "2025-04"      (기존 baseline 조건)
      B(pubdate) : published_at = 추정 발행일      (본 실험 조건)
  - 유일한 차이는 published_at. 채점 로직은 260615 와 동일.

발행일 추정 규칙(보도시점):
  - gold period 들 중 미래추계(연도>2026)·과거인용만인 것을 제외한 '최신 보도 period'
    + 1개월 = 발행일(월간 통계 보도 지연 모사).
  - gold 가 '과거 앵커'만 담은 기사(N개월/년 만에·전년 기저 등)는 claim 의 상대표현으로
    현재 시점을 계산해 손보정(_OVERRIDES). 절대연도 인용 기사는 base 영향이 없어 무해.

실행:  uv run x python benchmark/260617_2~5_gold-figure-recall-pubdate_leeaain/260617_2~5_gold-figure-recall-pubdate_leeaain.py [--limit N] [--concurrency K]
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

HERE = Path(__file__).parent
BASE = HERE.name
DATA = Path("benchmark/data/2~6_from_labeled_true_source.jsonl")
OUTJSON = HERE / f"{BASE}_result.json"
OUTMD = HERE / f"{BASE}_report.md"

DUMMY_DATE = "2025-04"

# gold 가 과거앵커만 담아 기계규칙(최신 period+1m)이 비현실적이 되는 기사 → claim 상대표현으로 보도시점 손보정.
_OVERRIDES = {
    11: "2025-04",   # 쉬었음 인구 월간(고용동향); gold 가 annual 2025 로 오라벨
    28: "2025-06",   # 단기근로자 2014 vs 2025 비교
    30: "2025-06",
    44: "2025-04",   # 생활물가 "지난해 10월(저점)" → 현재 2025
    49: "2025-02",   # 신선식품 "2022.3 이후 34개월" → 2025-01
    54: "2025-04",   # "2021.6 이후 3년9개월" → 2025-03
    68: "2025-10",   # 물가 "전년 9월 기저" → 현재 2025-09
    76: "2025-10",   # "지난해 2월 이후 1년7개월" → 2025-09
    87: "2025-02",   # 출생아 1986~1995 역사비교(절대연도)
    90: "2025-02",   # 출생아 "2015 이후 9년" → 2024
    103: "2025-05",  # 분기 출산율 "2023 1분기 이후 2년" → 2025-Q1
    116: "2025-01",  # "2020.12 이후 4년" → 2024-12
    117: "2025-04",  # 청년고용률 탄핵기 분석(절대연도)
    118: "2025-04",
    119: "2025-04",
    121: "2025-02",  # "2003 이후 21년" → 2024
    122: "2025-02",  # 소매판매 코로나 narrative
    123: "2025-02",  # 소매판매 2022/2023
}


# --------------------------------------------------------------------------- #
# 발행일 추정
# --------------------------------------------------------------------------- #
def _parse_ym(p) -> tuple[int, int] | None:
    p = str(p or "").strip()
    if not p:
        return None
    if "~" in p:
        left, right = (x.strip() for x in p.split("~", 1))
        if re.match(r"\d{4}", right):
            return _parse_ym(right)
        ly = re.match(r"(\d{4})", left)
        if ly and re.match(r"^\d{1,2}$", right):     # "2024-09~12"
            return (int(ly.group(1)), int(right))
        return _parse_ym(left)
    m = re.match(r"(\d{4})-Q([1-4])", p)
    if m:
        return (int(m.group(1)), int(m.group(2)) * 3)
    m = re.match(r"(\d{4})[-.](\d{1,2})", p)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = re.match(r"^(\d{4})$", p)
    if m:
        return (int(m.group(1)), 12)
    return None


def _plus1m(ym: tuple[int, int]) -> tuple[int, int]:
    y, mn = ym
    return (y + 1, 1) if mn >= 12 else (y, mn + 1)


def realistic_pubdate(rec: dict) -> str:
    """보도시점 추정 발행일(YYYY-MM). 손보정 우선, 없으면 최신 보도 period(+1개월)."""
    if rec["id"] in _OVERRIDES:
        return _OVERRIDES[rec["id"]]
    cands = [_parse_ym(g.get("period")) for g in rec.get("gold", [])]
    cands = [c for c in cands if c and c[0] <= 2026]      # 미래추계 제외
    if not cands:
        return DUMMY_DATE
    y, mn = _plus1m(max(cands))
    return f"{y}-{mn:02d}"


# --------------------------------------------------------------------------- #
# 채점 (260615 와 동일)
# --------------------------------------------------------------------------- #
def canon_period(p) -> str | None:
    p = str(p or "").strip()
    if "~" in p:
        return None
    m = re.match(r"^(\d{4})-Q([1-4])$", p)
    if m:
        return f"{m.group(1)}{int(m.group(2)) * 3:02d}"   # 분기→분기말월(채점 정합)
    m = re.match(r"^(\d{4})-(\d{2})$", p)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    if re.match(r"^\d{4}$", p):
        return p
    d = re.sub(r"\D", "", p)
    return d or None


def vmatch(e, g, rtol=0.01, atol=0.5) -> bool:
    try:
        e, g = float(e), float(g)
    except (TypeError, ValueError):
        return False
    return abs(e - g) <= max(atol, rtol * abs(g))


_DELTA_KW = ("증감", "증가", "감소", "전년", "전월", "대비")


def gold_type(item: str | None) -> str:
    return "delta" if any(k in (item or "") for k in _DELTA_KW) else "absolute"


def _evidences(ms: MasterSchema) -> list[dict]:
    return [
        {"period": ev.period, "value": ev.value, "unit": ev.unit,
         "item_id": ev.kosis_item_id, "tbl": ev.kosis_tbl_id, "tbl_nm": ev.table_name}
        for an in ms.analysis for ev in (an.evidences or [])
    ]


def _score(evs: list[dict], gold: list[dict]) -> list[dict]:
    out = []
    for g in gold:
        gv, gp = g.get("value"), g.get("period")
        if gv is None or isinstance(gv, list):
            out.append({"gold": g, "kind": "range_or_none", "value_hit": None, "vp_hit": None})
            continue
        vhit = any(vmatch(e["value"], gv) for e in evs)
        matched = next(
            (e for e in evs if vmatch(e["value"], gv) and canon_period(e["period"]) == canon_period(gp)),
            next((e for e in evs if vmatch(e["value"], gv)), None),
        )
        vphit = matched is not None and canon_period(matched["period"]) == canon_period(gp)
        out.append({"gold": g, "kind": "single", "type": gold_type(g.get("item")),
                    "value_hit": vhit, "vp_hit": vphit, "matched_ev": matched})
    return out


# --------------------------------------------------------------------------- #
# 실행 (record당 [1][2] 1회 → fork[3][4][5] ×2)
# --------------------------------------------------------------------------- #
async def _branch(ms: MasterSchema, pubdate: str, gold: list[dict]) -> dict:
    ms.article.published_at = pubdate
    err = None
    for fn in (normalize_claim, retrieve_kosis_candidates, fetch_kosis_data):
        try:
            await fn(ms)
        except Exception as exc:           # noqa: BLE001 — 단계 실패 기록용
            err = f"{fn.__name__}: {exc}"
            break
    evs = _evidences(ms)
    return {"pubdate": pubdate, "ok": err is None, "error": err,
            "n_evidences": len(evs), "evidences": evs, "gold_results": _score(evs, gold)}


async def _run_one(rec: dict) -> dict:
    gold = rec.get("gold", [])
    pub_b = realistic_pubdate(rec)
    ms = MasterSchema(content=rec["claim"])
    t0 = time.perf_counter()
    head_err = None
    for fn in (load_article, extract_statistical_claims):     # [1][2] 공유
        try:
            await fn(ms)
        except Exception as exc:                              # noqa: BLE001
            head_err = f"{fn.__name__}: {exc}"
            break

    if head_err:
        empty = {"ok": False, "error": head_err, "n_evidences": 0, "evidences": [], "gold_results": []}
        a = {**empty, "pubdate": DUMMY_DATE}
        b = {**empty, "pubdate": pub_b}
    else:
        a = await _branch(ms.model_copy(deep=True), DUMMY_DATE, gold)   # baseline 재현
        b = await _branch(ms.model_copy(deep=True), pub_b, gold)        # 실험
    dur = round(time.perf_counter() - t0, 2)
    return {
        "id": rec["id"], "claim": rec["claim"][:70], "duration_s": dur,
        "n_claims": len(ms.claims), "subjects": [c.subject for c in ms.claims],
        "head_error": head_err, "dummy": a, "pubdate": b,
    }


async def _run_all(rows: list[dict], conc: int) -> list[dict]:
    sem = asyncio.Semaphore(conc)
    total = len(rows)
    done = [0]

    async def guarded(rec):
        async with sem:
            r = await _run_one(rec)
            done[0] += 1
            da = sum(1 for g in r["dummy"]["gold_results"] if g.get("type") == "absolute" and g["vp_hit"])
            db = sum(1 for g in r["pubdate"]["gold_results"] if g.get("type") == "absolute" and g["vp_hit"])
            flag = "→Δ" if (da != db or r["dummy"]["n_evidences"] != r["pubdate"]["n_evidences"]) else "  "
            print(f"[{done[0]:>3}/{total}] {flag} dummy(ev={r['dummy']['n_evidences']},vp={da}) "
                  f"pub[{r['pubdate']['pubdate']}](ev={r['pubdate']['n_evidences']},vp={db}) | {r['claim'][:30]}…")
            return r

    return sorted(await asyncio.gather(*(guarded(x) for x in rows)), key=lambda r: r["id"])


def _summ(items: list[dict], key: str) -> dict:
    branch = [it[key] for it in items]
    single = [g for b in branch for g in b["gold_results"] if g["kind"] == "single"]
    absol = [g for g in single if g["type"] == "absolute"]
    delta = [g for g in single if g["type"] == "delta"]
    a_vh = sum(1 for g in absol if g["value_hit"])
    a_vph = sum(1 for g in absol if g["vp_hit"])
    return {
        "records_ok": sum(1 for b in branch if b["ok"]),
        "records_with_evidence": sum(1 for b in branch if b["n_evidences"] > 0),
        "total_evidences": sum(b["n_evidences"] for b in branch),
        "gold_absolute": len(absol),
        "gold_delta_unwired": len(delta),
        "abs_value_hits": a_vh,
        "abs_value_period_hits": a_vph,
        "abs_value_recall": round(a_vh / len(absol), 4) if absol else 0.0,
        "abs_value_period_recall": round(a_vph / len(absol), 4) if absol else 0.0,
        "delta_value_hits": sum(1 for g in delta if g["value_hit"]),
    }


def _changed_records(items: list[dict]) -> list[dict]:
    """vp_hit 또는 evidence 수가 두 조건 간 달라진 record(원인 진단용)."""
    out = []
    for it in items:
        da = sum(1 for g in it["dummy"]["gold_results"] if g.get("type") == "absolute" and g["vp_hit"])
        db = sum(1 for g in it["pubdate"]["gold_results"] if g.get("type") == "absolute" and g["vp_hit"])
        if da != db or it["dummy"]["n_evidences"] != it["pubdate"]["n_evidences"]:
            out.append({"id": it["id"], "claim": it["claim"], "pubdate_B": it["pubdate"]["pubdate"],
                        "date_differs": it["pubdate"]["pubdate"] != DUMMY_DATE,  # False=같은날짜→순수 노이즈
                        "vp_dummy": da, "vp_pubdate": db,
                        "ev_dummy": it["dummy"]["n_evidences"], "ev_pubdate": it["pubdate"]["n_evidences"]})
    return out


def _md(sd: dict, sp: dict, n: int, n_diff: int, changed: list[dict]) -> str:
    def row(label, kd, kp, fmt="{}"):
        return f"| {label} | {fmt.format(kd)} | {fmt.format(kp)} |"
    L = [f"# {BASE}", "",
         "## 1. 개요",
         "기존 260615 테스트는 발행일(`published_at`)을 더미 `2025-04` 로 고정했다. 본 테스트는 "
         "발행일을 **보도시점 추정값**으로 채웠을 때 [5] gold figure recall 이 바뀌는지를 "
         "**통제 비교**한다. record 당 [1][2]를 한 번만 실행해 동일 추출 claim 을 공유하고, "
         "이후 발행일만 다른 두 갈래로 [3][4][5]를 돌렸다(추출 LLM 비결정성 제거).", "",
         "## 2. 무엇을 테스트했나",
         f"- 골드셋: `{DATA}` ({n}건, 전부 label=True)",
         "- 채점 대상: [5] fetch_kosis_data 가 gold(원본 통계표 수치)를 재현했는가 (값 / 값+시점).",
         "- 조건 A(dummy): published_at=`2025-04` (기존 baseline 재현)",
         "- 조건 B(pubdate): published_at=보도시점 추정(미래추계·과거인용 보정)", "",
         "## 3. 결과 — 더미 vs 보도시점 추정", "",
         "| 지표 | A: dummy(2025-04) | B: pubdate(추정) |",
         "|---|---|---|",
         row("evidence 확보 record", sd["records_with_evidence"], sp["records_with_evidence"], "{}/" + str(n)),
         row("확보 evidence 총수", sd["total_evidences"], sp["total_evidences"]),
         row("절대값형 gold(분모)", sd["gold_absolute"], sp["gold_absolute"]),
         f"| **절대값 재현율 (값)** | **{sd['abs_value_recall']:.3f}** ({sd['abs_value_hits']}/{sd['gold_absolute']}) | "
         f"**{sp['abs_value_recall']:.3f}** ({sp['abs_value_hits']}/{sp['gold_absolute']}) |",
         f"| **절대값 재현율 (값+시점)** ★ | **{sd['abs_value_period_recall']:.3f}** ({sd['abs_value_period_hits']}/{sd['gold_absolute']}) | "
         f"**{sp['abs_value_period_recall']:.3f}** ({sp['abs_value_period_hits']}/{sp['gold_absolute']}) |",
         row("증감형 적중(참고)", f"{sd['delta_value_hits']}/{sd['gold_delta_unwired']}",
             f"{sp['delta_value_hits']}/{sp['gold_delta_unwired']}"),
         "",
         f"> ★ 값+시점이 더 엄격한 신뢰 지표. 두 조건의 유일한 차이는 발행일(상대시점 base)이다.", "",
         "## 4. 두 조건 간 달라진 record", "",
         "[3][4][5]는 LLM·KOSIS 호출이라 **발행일이 같아도(B==2025-04)** 재실행 시 결과가 흔들린다. "
         "그래서 변화 record 를 ① 날짜가 실제로 다른 것(=발행일 효과 후보)과 ② 날짜가 같은데 변한 것"
         "(=순수 노이즈)으로 나눈다.", ""]
    sig = [c for c in changed if c["date_differs"]]
    noise = [c for c in changed if not c["date_differs"]]
    L += [f"- 발행일이 dummy 와 다른 record: {n_diff}/{n}건",
          f"- 변화 record: 총 {len(changed)} = 날짜다름 {len(sig)} + 날짜같음(노이즈) {len(noise)}", ""]
    if sig:
        L += ["**① 날짜 다름 (발행일 효과 후보)**", "",
              "| id | pubdate_B | vp(dummy→pub) | ev(dummy→pub) | claim |", "|---|---|---|---|---|"]
        L += [f"| {c['id']} | {c['pubdate_B']} | {c['vp_dummy']}→{c['vp_pubdate']} | "
              f"{c['ev_dummy']}→{c['ev_pubdate']} | {c['claim'][:42]}… |" for c in sig]
        L += [""]
    if noise:
        L += ["**② 날짜 같음 (재실행 노이즈)**", "",
              "| id | vp(dummy→pub) | ev(dummy→pub) |", "|---|---|---|"]
        L += [f"| {c['id']} | {c['vp_dummy']}→{c['vp_pubdate']} | {c['ev_dummy']}→{c['ev_pubdate']} |"
              for c in noise]
    if not changed:
        L += ["_변화 없음._"]
    L += ["", "## 5. 한계",
          "- 발행일은 메타데이터가 아니라 gold·claim 상대표현 기반 **추정**(절대연도 인용 기사는 base 영향 없음).",
          "- 채점은 [5] 값 한정([2] subject·[3] 값정규화 정답 없음). 증감형 156·범위형은 단일셀 대조 불가.",
          "- 두 조건이 [1][2] 추출을 공유 → A 수치는 기존 260615(추출 별도 실행)와 LLM 비결정성으로 다를 수 있음."]
    return "\n".join(L)


def _read(path: Path, limit: int) -> list[dict]:
    rows = [json.loads(s) for ln in path.read_text(encoding="utf-8").splitlines()
            if (s := ln.strip()).startswith("{")]
    return rows[:limit] if limit else rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=6)
    args = ap.parse_args()

    rows = _read(DATA, args.limit)
    print(f"발행일 통제 비교 시작 — {len(rows)}건, 동시 {args.concurrency} (record당 [1][2]1회 + fork ×2)\n")
    items = asyncio.run(_run_all(rows, args.concurrency))

    sd, sp = _summ(items, "dummy"), _summ(items, "pubdate")
    changed = _changed_records(items)
    n_diff = sum(1 for it in items if it["pubdate"]["pubdate"] != DUMMY_DATE)
    OUTJSON.write_text(json.dumps(
        {"source": str(DATA), "stages": "2-5(채점=5)", "conditions": {"A": DUMMY_DATE, "B": "보도시점 추정"},
         "records_with_date_diff": n_diff,
         "summary_dummy": sd, "summary_pubdate": sp, "changed_records": changed, "records": items},
        ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    OUTMD.write_text(_md(sd, sp, len(rows), n_diff, changed), encoding="utf-8")

    print(f"\nA(dummy)   : {json.dumps(sd, ensure_ascii=False)}")
    print(f"B(pubdate) : {json.dumps(sp, ensure_ascii=False)}")
    print(f"변화 record: {len(changed)}")
    print(f"저장: {OUTJSON}\n      {OUTMD}")


if __name__ == "__main__":
    main()
