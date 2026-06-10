"""[5] 메타데이터 조회 — 첫 키워드(경제성장률)의 후보 10개 표 각각의 메타를 받아온다.

흐름(실제 배선):
  [4] search_tables(subject)            → 후보 통계표 10개 (tbl_id)
  [5] fetch_table_metadata(org, tbl)    → 표별 항목·분류축(obj_id)·주기  ← 검증 대상

입력: tests/data_KOSIS_(2)통계표메타데이터조회_30개.txt 의 **첫 줄**(subject, population).
표마다 메타가 다른 것을 확인하기 위해, 후보 10개 각각의 메타를 받아 저장한다.
기존 모듈만 호출(부가 로직 없음). 결과는 tests/results/ 에 md+json 저장(CLAUDE.md 규칙).

검증 대상: src/kosis/metadata.py (fetch_table_metadata) — [5]가 쓰는 메타 모듈
도구: src/kosis/search.py (search_tables, 후보 10개 확보용)
    uv run x python tests/260610_5_metadata-candidates_leeaain.py
"""
from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

from src.kosis import KosisError, fetch_table_metadata, search_tables

load_dotenv()

DATA = Path(__file__).parent / "data_KOSIS_(2)통계표메타데이터조회_30개.txt"
OUT_MD = Path(__file__).parent / "results" / "260610_5_metadata-candidates_leeaain.md"
OUT_JSON = OUT_MD.with_suffix(".json")


def main() -> None:
    # 첫 줄: "subject, population"
    first = DATA.read_text(encoding="utf-8").splitlines()[0]
    subject, _, population = first.partition(",")
    subject, population = subject.strip(), population.strip()

    candidates = search_tables(subject, top_n=10)  # [4] 후보 10개 (tbl_id 확보)

    rows = []
    for c in candidates:
        rec = {"org_id": c.org_id, "tbl_id": c.tbl_id, "tbl_nm": c.tbl_nm}
        try:
            meta = fetch_table_metadata(c.org_id, c.tbl_id)  # [5] 메타 모듈
            rec.update(
                ok=True,
                item_count=len(meta.items),
                axis_count=meta.axis_count,
                period_count=len(meta.periods),
                axes=[{"obj_id": a.obj_id, "name": a.name, "values": len(a.values)} for a in meta.axes],
                schema=meta.to_dict(),
            )
        except (KosisError, ValueError) as exc:
            rec.update(ok=False, error=f"{type(exc).__name__}: {exc}")
        rows.append(rec)

    ok = sum(1 for r in rows if r["ok"])
    OUT_MD.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(
        json.dumps({"subject": subject, "population": population,
                    "summary": {"total": len(rows), "ok": ok}, "results": rows},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# 260610_5_metadata-candidates_leeaain",
        "",
        "### 1. 테스트 목적",
        f"첫 키워드 '{subject}'(population '{population}')의 [4] 후보 10개 표 각각에 대해 "
        "[5] 메타데이터(fetch_table_metadata)를 받아 표마다 메타(항목·분류축·주기)가 다름을 확인.",
        "### 2. 검증 대상 모듈",
        "- src/kosis/metadata.py — fetch_table_metadata ([5]가 쓰는 메타 조회)",
        "### 3. 도구로만 쓰인 모듈 (검증대상 아님)",
        "- src/kosis/search.py — search_tables (후보 10개 확보용)",
        "### 4. 일자 / 작성자",
        "- 2026-06-10 / leeaain",
        "",
        f"### 5. 결과 (성공 {ok}/{len(rows)}) · 원자료: {OUT_JSON.name}",
        "",
        "| RANK | 통계표 | 표명 | 항목 | 분류축(obj_id:이름·값수) | 주기 |",
        "|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        if r["ok"]:
            axes = ", ".join(f"{a['obj_id']}:{a['name']}({a['values']})" for a in r["axes"]) or "(0축)"
            md.append(f"| {i} | {r['org_id']}/{r['tbl_id']} | {r['tbl_nm']} | {r['item_count']} | "
                      f"{axes} | {r['period_count']} |")
        else:
            md.append(f"| {i} | {r['org_id']}/{r['tbl_id']} | {r['tbl_nm']} | ✗ | {r['error']} | - |")
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"'{subject}' 후보 10개 메타 조회 성공 {ok}/{len(rows)}")
    for i, r in enumerate(rows, 1):
        if r["ok"]:
            print(f"  {i:2d}. ✓ {r['org_id']}/{r['tbl_id']}  항목{r['item_count']}·축{r['axis_count']}·"
                  f"주기{r['period_count']}  | {r['tbl_nm']}")
        else:
            print(f"  {i:2d}. ✗ {r['org_id']}/{r['tbl_id']}  {r['error']}  | {r['tbl_nm']}")
    print(f"\n저장: {OUT_MD.name}, {OUT_JSON.name}")


if __name__ == "__main__":
    main()
