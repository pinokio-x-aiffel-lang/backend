"""v1 vs v2 recall 비교 리포트 생성.

실행:
    uv run python scripts/compare_recall.py
"""
import json
from pathlib import Path

V1_PATH = "scripts/recall_50_results_baseline.json"
V2_PATH = "scripts/recall_50_results_v2.json"
OUT_PATH = "scripts/recall_compare.md"


def load(path: str) -> dict[int, dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {r["idx"]: r for r in data}


def top1_stat(hits: list[dict]) -> str:
    if not hits:
        return "(없음)"
    h = hits[0]
    if h.get("error"):
        return f"오류: {h['error'][:40]}"
    return f"{h['tbl_nm']} [{h.get('stat_nm','')}]"


def top1_tbl_id(hits: list[dict]) -> str:
    if not hits or hits[0].get("error"):
        return ""
    return hits[0].get("tbl_id", "")


def is_sijungu(hits: list[dict]) -> bool:
    return bool(hits) and hits[0].get("stat_nm") == "시군구통계"


def is_international(hits: list[dict]) -> bool:
    if not hits or hits[0].get("error"):
        return False
    return hits[0].get("tbl_id", "").startswith("DT_2")


v1 = load(V1_PATH)
v2 = load(V2_PATH)

lines = []
lines.append("# Recall 개선 비교 — v1 vs v2")
lines.append("")
lines.append("> baseline: 공백 제거만 / v2: 국가 접두어 제거 + 시군구·국제통계 후순위 (동일 시점 비교)")
lines.append("")

# ── 집계 ──────────────────────────────────────────────────────────────────
keyword_changed_cases = []   # 검색어 바뀐 케이스
rerank_changed_cases = []    # 1위 표가 바뀐 케이스 (keyword 동일해도)

for idx in sorted(v1.keys()):
    r1 = v1[idx]
    r2 = v2[idx]

    for subj in r1.get("kosis", {}):
        if subj not in r2.get("kosis", {}):
            continue
        kw_v1 = "".join(subj.split())      # v1은 keyword_map 없음
        kw_v2 = r2.get("keyword_map", {}).get(subj, kw_v1)
        hits1 = r1["kosis"][subj]
        hits2 = r2["kosis"][subj]

        kw_changed = kw_v1 != kw_v2
        top1_changed = top1_tbl_id(hits1) != top1_tbl_id(hits2)

        if kw_changed:
            keyword_changed_cases.append((idx, subj, kw_v1, kw_v2, hits1, hits2))
        elif top1_changed:
            rerank_changed_cases.append((idx, subj, kw_v1, hits1, hits2))

# 시군구·국제통계가 v1에서 1위였다가 v2에서 내려간 케이스
v1_sijungu_top1 = sum(
    1 for r in v1.values()
    for hits in r.get("kosis", {}).values()
    if is_sijungu(hits)
)
v2_sijungu_top1 = sum(
    1 for r in v2.values()
    for hits in r.get("kosis", {}).values()
    if is_sijungu(hits)
)
v1_intl_top1 = sum(
    1 for r in v1.values()
    for hits in r.get("kosis", {}).values()
    if is_international(hits)
)
v2_intl_top1 = sum(
    1 for r in v2.values()
    for hits in r.get("kosis", {}).values()
    if is_international(hits)
)

lines.append("## 요약 집계")
lines.append("")
lines.append("| 지표 | v1 | v2 | 개선 |")
lines.append("|---|---|---|---|")
lines.append(f"| 시군구통계가 1위인 케이스 | {v1_sijungu_top1}건 | {v2_sijungu_top1}건 | {v1_sijungu_top1 - v2_sijungu_top1:+d} |")
lines.append(f"| 국제통계(DT_2*)가 1위인 케이스 | {v1_intl_top1}건 | {v2_intl_top1}건 | {v1_intl_top1 - v2_intl_top1:+d} |")
lines.append(f"| 검색어 변경된 케이스 | - | {len(keyword_changed_cases)}건 | - |")
lines.append(f"| 검색어 동일하나 1위 변경된 케이스 | - | {len(rerank_changed_cases)}건 | - |")
lines.append("")

# ── 검색어 바뀐 케이스 상세 ───────────────────────────────────────────────
lines.append("## 검색어가 바뀐 케이스 (국가 접두어 제거)")
lines.append("")
if not keyword_changed_cases:
    lines.append("> 없음")
else:
    for idx, subj, kw1, kw2, hits1, hits2 in keyword_changed_cases:
        lines.append(f"### [{idx:02d}] subject: `{subj}`")
        lines.append(f"- v1 keyword: `{kw1}`")
        lines.append(f"- v2 keyword: `{kw2}`")
        lines.append("")
        lines.append("| | 1위 | 2위 | 3위 |")
        lines.append("|---|---|---|---|")

        def fmt_hit(hits, i):
            if i >= len(hits): return "(없음)"
            h = hits[i]
            if h.get("error"): return f"오류"
            return f"{h['tbl_nm']} `{h.get('tbl_id','')}`"

        lines.append(f"| v1 | {fmt_hit(hits1,0)} | {fmt_hit(hits1,1)} | {fmt_hit(hits1,2)} |")
        lines.append(f"| v2 | {fmt_hit(hits2,0)} | {fmt_hit(hits2,1)} | {fmt_hit(hits2,2)} |")
        lines.append("")
lines.append("")

# ── 재정렬로 1위가 바뀐 케이스 ───────────────────────────────────────────
lines.append("## 재정렬로 1위가 바뀐 케이스 (시군구·국제통계 후순위 이동)")
lines.append("")
if not rerank_changed_cases:
    lines.append("> 없음")
else:
    for idx, subj, kw, hits1, hits2 in rerank_changed_cases:
        tag1 = "[시군구]" if is_sijungu(hits1) else ("[국제]" if is_international(hits1) else "")
        lines.append(f"### [{idx:02d}] subject: `{subj}` (keyword: `{kw}`)")
        lines.append(f"- v1 1위: {tag1} {top1_stat(hits1)}")
        lines.append(f"- v2 1위: {top1_stat(hits2)}")
        lines.append("")
        lines.append("| | 1위 | 2위 | 3위 |")
        lines.append("|---|---|---|---|")

        def fmt_hit2(hits, i):
            if i >= len(hits): return "(없음)"
            h = hits[i]
            if h.get("error"): return "오류"
            tag = ""
            if h.get("stat_nm") == "시군구통계": tag = "[시군구] "
            elif h.get("tbl_id", "").startswith("DT_2"): tag = "[국제] "
            return f"{tag}{h['tbl_nm']} `{h.get('tbl_id','')}`"

        lines.append(f"| v1 | {fmt_hit2(hits1,0)} | {fmt_hit2(hits1,1)} | {fmt_hit2(hits1,2)} |")
        lines.append(f"| v2 | {fmt_hit2(hits2,0)} | {fmt_hit2(hits2,1)} | {fmt_hit2(hits2,2)} |")
        lines.append("")

out = "\n".join(lines)
Path(OUT_PATH).write_text(out, encoding="utf-8")
print(f"저장 완료 -> {OUT_PATH}")
print(f"검색어 변경: {len(keyword_changed_cases)}건 / 재정렬 변경: {len(rerank_changed_cases)}건")
