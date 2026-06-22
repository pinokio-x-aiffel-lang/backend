"""4단계 값-기반 Recall — 후보표가 figure 값을 실제로 담는지 KOSIS raw로 확인.

비순환: 값=SSOT figure(사람검수), 후보=파이프라인 캡처 출력, 확인=raw call_kosis(파이프라인 함수 미사용).
정답 '표' 라벨링 불필요 — figure 값이 후보표 중 하나에 있으면 hit. 전 T행 채점 가능.
gold_rank = 값이 처음 발견된 후보 순위 → score_retrieve로 Recall@N/MRR.

실행: uv run x python benchmark_aain/value_recall_4.py
출력: benchmark/4_retrieve/leeaain_<날짜>_NN.{jsonl,md}  (save_result)
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from src.kosis import KosisError, call_kosis, fetch_table_metadata, resolve_api_key

from benchmark.reporting import save_result, blank_sections
from benchmark.scoring import score_retrieve

ROOT = Path(__file__).resolve().parent.parent
SSOT = ROOT / "benchmark/data/ssot/260614_master_eval_213_parsed_human_checked_SSOT.jsonl"
S4 = ROOT / "benchmark/data/4_retrieve/4_source_1.jsonl"


def _load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def _period(p):
    p = str(p or "").strip()
    if not p or "~" in p:
        return None, None
    if "Q" in p.upper():
        y, q = p.upper().replace("-", "").split("Q")[:2]
        return f"{y}Q{q}", "Q"
    if "-" in p:
        a, b = p.split("-")[:2]
        return (f"{a}{int(b):02d}", "M") if b.isdigit() and len(b) <= 2 else (a, "Y")
    return p, "Y"


def _close(a, b):
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= max(0.05, abs(b) * 0.01)


_meta, _rows = {}, {}


def has_value(org, tbl, period, pse, value, api_key):
    key = (tbl, period)
    if key not in _rows:
        try:
            if tbl not in _meta:
                _meta[tbl] = fetch_table_metadata(org, tbl)
            meta = _meta[tbl]
            itm = "+".join(i.itm_id for i in meta.items[:30]) or "ALL"
            params = {"method": "getList", "apiKey": api_key, "itmId": itm, "objL": "ALL",
                      "format": "json", "jsonVD": "Y", "prdSe": "H" if pse == "S" else pse,
                      "startPrdDe": period, "endPrdDe": period, "orgId": org, "tblId": tbl}
            for n in range(1, min(max(1, len(meta.axes)), 4) + 1):
                params[f"objL{n}"] = "ALL"
            _rows[key] = call_kosis(params)
        except (KosisError, ValueError):
            _rows[key] = []
    return any(isinstance(r, dict) and r.get("PRD_DE") == period and _close(r.get("DT"), value)
               for r in _rows[key])


def main():
    api_key = resolve_api_key()
    ssot = {r["row_id"]: r for r in _load(SSOT)}
    # row_id → 후보표 union (min rank)
    cand = defaultdict(dict)
    for r in _load(S4):
        for c in (r.get("candidates") or []):
            rk = c.get("rank", 99)
            t = c.get("tbl_id")
            if t and (t not in cand[r["row_id"]] or rk < cand[r["row_id"]][t][1]):
                cand[r["row_id"]][t] = (c.get("org_id", "101"), rk)

    records = []
    for rid, row in ssot.items():
        if row["label"] != "T":
            continue
        cands = sorted(cand.get(rid, {}).items(), key=lambda x: x[1][1])  # (tbl,(org,rank)) by rank
        for gf in (row.get("gold_figures") or []):
            v = gf.get("value")
            if v is None or isinstance(v, list):
                continue
            pde, pse = _period(gf.get("period"))
            if not pde:
                continue
            vrank = None
            for i, (tbl, (org, _)) in enumerate(cands, 1):
                if has_value(org, tbl, pde, pse, v, api_key):
                    vrank = i
                    break
            records.append({"row_id": rid, "stage": 4, "label": "T",
                            "input": {"claims": [{"item": gf.get("item")}]},
                            "output": {"candidates": [t for t, _ in cands]},
                            "gold": {"figure_value": v, "period": pde},
                            "gold_rank": vrank, "success": bool(cands)})
            print(f"  {'✓' if vrank else '·'} row{rid} {gf.get('item')!r} {pde}={v} → value_rank={vrank} (cands={len(cands)})")

    m = score_retrieve(records)
    sec = blank_sections()
    sec["개요"] = "4단계 **값-기반 Recall** — 파이프라인이 검색한 후보표(candidates) 중 하나라도 figure 값을 실제로 담고 있는지 KOSIS raw로 확인. 정답 '표' 라벨링 없이 figure 값(SSOT, 독립)만으로 측정."
    sec["테스트 방법"] = (
        f"T {len(records)}개 figure 대상. 각 figure의 값을 후보표들에서 raw call_kosis로 순위대로 조회 "
        "→ 값이 처음 든 후보 순위=gold_rank → Recall@N/MRR. 비순환(값=독립, 후보=캡처, 확인=raw KOSIS).\n\n"
        "**데이터 출처 (골든셋 ≠ 입력, 서로 다른 파일)**\n"
        "- 골든셋(정답): `benchmark/data/ssot/260614_master_eval_213_parsed_human_checked_SSOT.jsonl` 의 "
        "`gold_figures` — T행 figure 값(사람검수·독립). 채점 기준.\n"
        "- 입력(채점 대상): `benchmark/data/4_retrieve/4_source_1.jsonl` 의 `candidates` — "
        "파이프라인이 검색한 후보 표 풀(캡처). `gold_tbl_id` 칸은 비움(표-라벨링 대신 값-기반 채점).\n"
        "- 채점 질문: 입력(후보 풀)이 골든셋 figure 값을 담고 있나 → gold_rank.")
    sec["분석"] = (
        "**Recall@N 읽는 법**: @ 뒤 숫자 = 상위 몇 개 후보까지 보는가. "
        "@1=정답이 1순위 / @3=상위 3개 안 / @10=상위 10개 안 비율. 넓게 볼수록(N↑) 값 상승, 만점 1.0. "
        "한 번의 테스트를 세 깊이에서 본 것.\n\n"
        "값-기반 Recall은 '검색이 값이 든 표를 가져왔나'를 본다(정본명 일치보다 시스템 목적에 부합). "
        "표 라벨링이 필요 없어 **전 T행 채점 가능**. 델타(증감) figure는 값이 셀에 없어 자연히 미검출 → 정직한 결과.")
    sec["개선 전후 비교"] = "표-기반 recall(leeaain_260619_01)과 비교: 표 유일성 제약을 없애 과소평가를 줄임."
    sec["한계·주의"] = ("① 후보(candidates)는 2026-06-14 캡처. ② 델타 figure는 단일 셀에 없어 미검출(검색 탓 아님). "
                    "③ 값-일치는 셀이 그 값을 담는다는 의미일 뿐, 항목/축 정합성은 별도(stage5).")
    j, d = save_result(4, "leeaain", records, m, sec)
    n = sum(1 for r in records if r["gold_rank"])
    print(f"\n값-기반 hit {n}/{len(records)} → {j.name}, {d.name}")
    for row in m:
        print("  ", row["지표"], row["값"], row["95% CI"])


if __name__ == "__main__":
    main()
