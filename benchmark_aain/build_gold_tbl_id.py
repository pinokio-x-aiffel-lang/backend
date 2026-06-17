"""gold_tbl_id 서브셋(73건) 빌드 — stage 4 표 recall / stage 5 셀 precision 진단 정답.

소스 두 갈래(무생성: 사람 라벨 + 값-검증 캡처에서만):
  ① 자동시드: 260617 cell-recall 베이스라인에서 값이 적중한 T 행 → 그 tbl_id 가 정답표.
  ② 병인님 라벨: from_origin_..._병인님라벨링.xlsx 의 F/M 60행. 사람이 라벨한
     정답 통계조사명+항목(`인구동향조사 — 합계출산율`) + 독립 공식값. 표명→tbl_id 는
     KOSIS 통합검색으로 resolve 하고 신뢰도 플래그를 단다(사람 검수용).

부가: resolve 된 정답표가 현재 stage 4 후보 top-N 안에 있는지(in_candidate_pool) 집계
      → 예비 stage 4 표 recall.

출력:
  data/260617_gold_tbl_id_subset.jsonl        # 정답 주석(병합용, 캐노니컬)
  data/260617_gold_tbl_id_subset_review.md     # 검수용 표(신뢰도 낮은 순)

실행:  uv run x python benchmark_aain/build_gold_tbl_id.py
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import openpyxl

from src.kosis import KosisError, search_tables

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "benchmark_aain/data"
SPINE = DATA / "260614_master_eval_213_parsed_human_checked.jsonl"
STAGE4 = DATA / "260614_source_from_origin_for_retrieve_kosis_candidates.jsonl"
BASELINE = (ROOT / "benchmark/260617_4~5_cell-recall-baseline_leeaain"
            / "260617_4~5_cell-recall-baseline_leeaain_result.json")
BYUNGIN = ROOT / "benchmark/data/from_origin_with_period_123_source_병인님라벨링.xlsx"
OUT_JSONL = DATA / "260617_gold_tbl_id_subset.jsonl"
OUT_MD = DATA / "260617_gold_tbl_id_subset_review.md"

_DASH = re.compile(r"\s*[—–]\s*")           # survey — item 구분자(em/en 대시만)
_PAREN = re.compile(r"\([^)]*\)")            # (전년대비)·(서울) 등 한정어


def _norm(s) -> str:
    return re.sub(r"[\s·\-—–~]", "", str(s or ""))


# --------------------------------------------------------------------------- #
# 로드
# --------------------------------------------------------------------------- #
def _load_jsonl(p: Path) -> list[dict]:
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines()
            if (s := ln.strip())]


def load_spine_textmap() -> list[tuple[str, dict]]:
    """(norm(text), spine_row) 목록 — 병인님 텍스트 매칭용."""
    return [(_norm(r["text"]), r) for r in _load_jsonl(SPINE) if r["label"] in ("F", "M")]


def match_row_id(text: str, spine: list[tuple[str, dict]]) -> dict | None:
    bn = _norm(text)[:30]
    for sn, row in spine:
        if sn[:30] == bn or sn.startswith(bn) or bn.startswith(sn[:30]):
            return row
    return None


def load_stage4_index():
    """row_id → {claim_ids, subject, candidate tbl_id set, tbl_id→tbl_nm}."""
    idx: dict[int, dict] = {}
    tbl_nm: dict[str, str] = {}
    for r in _load_jsonl(STAGE4):
        cands = r.get("candidates", [])
        for c in cands:
            tbl_nm.setdefault(c["tbl_id"], c.get("tbl_nm") or "")
        d = idx.setdefault(r["row_id"], {"claim_ids": [], "subject": r.get("subject"),
                                         "cand_tbls": set()})
        d["claim_ids"].append(r["claim_id"])
        d["cand_tbls"].update(c["tbl_id"] for c in cands)
    return idx, tbl_nm


def load_byungin() -> list[dict]:
    wb = openpyxl.load_workbook(BYUNGIN, read_only=True, data_only=True)
    out = []
    for sheet, lab in [("False", "F"), ("M-S", "M")]:
        for r in list(wb[sheet].iter_rows(values_only=True))[1:]:
            if r[0] and len(r) > 1 and r[1]:
                out.append({"label": lab, "text": str(r[0]), "tbl_name": str(r[1]),
                            "value_raw": str(r[2]) if len(r) > 2 and r[2] else None})
    wb.close()
    return out


# --------------------------------------------------------------------------- #
# 표명 → tbl_id resolve
# --------------------------------------------------------------------------- #
def parse_label(tbl_name: str) -> tuple[str | None, str]:
    """`인구동향조사 — 합계출산율` → (survey, item). 대시 없으면 (None, 원문)."""
    parts = _DASH.split(tbl_name, maxsplit=1)
    if len(parts) == 2:
        survey = _PAREN.sub("", parts[0]).strip()
        item = _PAREN.sub("", parts[1]).strip()
        return survey or None, item or tbl_name
    return None, _PAREN.sub("", tbl_name).strip() or tbl_name


def score_hit(hit, survey: str | None, item: str) -> int:
    """stat_nm 이 survey 와 맞으면 +2, tbl_nm 이 item 을 포함하면 +1."""
    s = 0
    if survey and (_norm(survey) in _norm(hit.stat_nm) or _norm(hit.stat_nm) in _norm(survey)):
        s += 2
    ni = _norm(item)
    if ni and ni in _norm(hit.tbl_nm):
        s += 1
    return s


_search_cache: dict[str, list] = {}


def resolve(tbl_name: str) -> dict:
    """병인님 표명 → 최적 (org_id, tbl_id, tbl_nm) + 신뢰도. 검색은 item 키워드로."""
    survey, item = parse_label(tbl_name)
    keyword = item  # 표명은 item 어휘에 가까움
    if keyword not in _search_cache:
        try:
            _search_cache[keyword] = search_tables(keyword, top_n=10)
        except (KosisError, ValueError):
            _search_cache[keyword] = []
    hits = _search_cache[keyword]
    if not hits:
        return {"gold_org_id": None, "gold_tbl_id": None, "gold_tbl_nm": None,
                "confidence": "none", "search_keyword": keyword, "n_hits": 0, "top3": []}
    scored = sorted(hits, key=lambda h: score_hit(h, survey, item), reverse=True)
    best = scored[0]
    bs = score_hit(best, survey, item)
    conf = "high" if bs >= 3 else "med" if bs >= 1 else "low"
    return {
        "gold_org_id": best.org_id, "gold_tbl_id": best.tbl_id, "gold_tbl_nm": best.tbl_nm,
        "confidence": conf, "search_keyword": keyword, "n_hits": len(hits),
        "parsed_survey": survey, "parsed_item": item,
        "top3": [{"tbl_id": h.tbl_id, "tbl_nm": h.tbl_nm, "stat_nm": h.stat_nm,
                  "score": score_hit(h, survey, item)} for h in scored[:3]],
    }


# --------------------------------------------------------------------------- #
# 빌드
# --------------------------------------------------------------------------- #
def build() -> list[dict]:
    s4idx, tbl_nm_map = load_stage4_index()
    rows: list[dict] = []

    # ① 자동시드 (값 적중 T 행)
    base = json.load(open(BASELINE, encoding="utf-8"))
    for r in base["records"]:
        if not r["value_hit"]:
            continue
        tbl = r["seed_gold_tbl_id"]
        rid = r["row_id"]
        rows.append({
            "row_id": rid, "claim_id": r["claim_id"], "label": r["label"],
            "source": "auto_seed",
            "gold_org_id": None, "gold_tbl_id": tbl, "gold_tbl_nm": tbl_nm_map.get(tbl),
            "gold_item_id": r["seed_gold_item_id"],
            "confidence": "value_match", "is_delta": r["is_delta"],
            "official_value": r["gold_value"],
            "in_candidate_pool": tbl in s4idx.get(rid, {}).get("cand_tbls", set()),
        })

    # ② 병인님 F/M (표명→tbl_id resolve)
    spine = load_spine_textmap()
    for b in load_byungin():
        srow = match_row_id(b["text"], spine)
        if srow is None:
            continue
        rid = srow["row_id"]
        res = resolve(b["tbl_name"])
        tbl = res["gold_tbl_id"]
        cand_tbls = s4idx.get(rid, {}).get("cand_tbls", set())
        rows.append({
            "row_id": rid, "claim_id": s4idx.get(rid, {}).get("claim_ids", [None])[0],
            "label": b["label"], "source": "byungin_resolved",
            "byungin_tbl_name": b["tbl_name"], "official_value_raw": b["value_raw"],
            "gold_org_id": res["gold_org_id"], "gold_tbl_id": tbl,
            "gold_tbl_nm": res["gold_tbl_nm"], "confidence": res["confidence"],
            "search_keyword": res["search_keyword"], "n_hits": res["n_hits"],
            "top3": res.get("top3", []),
            "in_candidate_pool": (tbl in cand_tbls) if tbl else False,
        })
    return rows


def render_review(rows: list[dict]) -> str:
    order = {"none": 0, "low": 1, "med": 2, "high": 3, "value_match": 4}
    rows_sorted = sorted(rows, key=lambda r: order.get(r["confidence"], 9))
    L = ["# gold_tbl_id 서브셋 검수표 (260617)", "",
         f"총 {len(rows)}건. 신뢰도 낮은 순(검수 우선). `in_pool`=정답표가 현 stage4 후보에 있나.", ""]
    L += ["| conf | label | src | row | gold_tbl_id | gold_tbl_nm | in_pool | 병인님 표명 / 공식값 |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows_sorted:
        name = r.get("byungin_tbl_name") or "(auto)"
        val = r.get("official_value_raw") or r.get("official_value") or ""
        L.append(f"| {r['confidence']} | {r['label']} | {r['source'][:4]} | {r['row_id']} | "
                 f"{r.get('gold_tbl_id') or '—'} | {str(r.get('gold_tbl_nm') or '')[:24]} | "
                 f"{'Y' if r.get('in_candidate_pool') else 'N'} | {name[:30]} / {val} |")
    return "\n".join(L) + "\n"


def main() -> None:
    rows = build()
    OUT_JSONL.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                         encoding="utf-8")
    OUT_MD.write_text(render_review(rows), encoding="utf-8")

    conf = Counter(r["confidence"] for r in rows)
    src = Counter(r["source"] for r in rows)
    in_pool = sum(1 for r in rows if r.get("in_candidate_pool"))
    resolved = sum(1 for r in rows if r.get("gold_tbl_id"))
    print(f"\n== gold_tbl_id 서브셋: {len(rows)}건 ==")
    print(f"  source: {dict(src)}")
    print(f"  confidence: {dict(conf)}")
    print(f"  tbl_id resolved: {resolved}/{len(rows)}")
    print(f"  in_candidate_pool(예비 stage4 표 recall): {in_pool}/{len(rows)}"
          f" = {in_pool/len(rows):.1%}")
    print(f"저장:\n  {OUT_JSONL}\n  {OUT_MD}")


if __name__ == "__main__":
    main()
