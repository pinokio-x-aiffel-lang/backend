"""[5] 메타데이터 조회 테스트 — [4] 결과의 (org_id, tbl_id)로 메타를 불러오는지 확인.

입력: tests/results/260610_4_kosis-search-keywords_leeaain.json ([4] 통계표 조회 결과)
      → 키워드별 RANK 1 통계표의 (org_id, tbl_id) 를 추출(중복 제거).
기존 모듈 src.kosis.fetch_table_metadata 만 호출(부가 로직 없음)해 항목·분류축(obj_id)·
주기가 정상 파싱되는지 본다. 결과는 tests/results/ 에 md+json 저장(CLAUDE.md 규칙).

검증 대상: src/kosis/metadata.py (fetch_table_metadata)
    uv run x python tests/260610_5_metadata-from-search_leeaain.py
"""
from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

from src.kosis import KosisError, fetch_table_metadata

load_dotenv()

SEARCH_JSON = Path(__file__).parent / "results" / "260610_4_kosis-search-keywords_leeaain.json"
OUT_MD = Path(__file__).parent / "results" / "260610_5_metadata-from-search_leeaain.md"
OUT_JSON = OUT_MD.with_suffix(".json")


def _tables() -> list[tuple[str, str, str]]:
    """[4] 결과 json 에서 키워드별 RANK 1 (org_id, tbl_id, tbl_nm) 추출 — 중복 제거."""
    data = json.loads(SEARCH_JSON.read_text(encoding="utf-8"))
    out, seen = [], set()
    for r in data["results"]:
        cands = r.get("candidates") or []
        if not cands:
            continue
        c = cands[0]  # RANK 1
        key = (c["org_id"], c["tbl_id"])
        if key not in seen:
            seen.add(key)
            out.append((c["org_id"], c["tbl_id"], c["tbl_nm"]))
    return out


def main() -> None:
    tables = _tables()
    rows = []
    for org_id, tbl_id, tbl_nm in tables:
        rec = {"org_id": org_id, "tbl_id": tbl_id, "tbl_nm": tbl_nm}
        try:
            meta = fetch_table_metadata(org_id, tbl_id)  # 기존 모듈만 호출
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
        json.dumps({"summary": {"total": len(rows), "ok": ok}, "results": rows},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# 260610_5_metadata-from-search_leeaain",
        "",
        "### 1. 테스트 목적",
        "[4] 통계표 조회 결과의 (org_id, tbl_id)로 [5] 메타데이터(fetch_table_metadata)가 "
        "항목·분류축(obj_id)·주기를 정상 조회·파싱하는지 확인.",
        "### 2. 검증 대상 모듈",
        "- src/kosis/metadata.py — fetch_table_metadata",
        "### 3. 도구로만 쓰인 모듈 (검증대상 아님)",
        "- 없음 (입력은 260610_4_kosis-search-keywords_leeaain.json 에서 읽음)",
        "### 4. 일자 / 작성자",
        "- 2026-06-10 / leeaain",
        "",
        f"### 5. 결과 (성공 {ok}/{len(rows)}) · 원자료: {OUT_JSON.name}",
        "",
        "| 통계표 | 표명 | 항목 | 분류축(obj_id) | 주기 |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        if r["ok"]:
            axes = ", ".join(f"{a['obj_id']}:{a['name']}" for a in r["axes"]) or "(0축)"
            md.append(f"| {r['org_id']}/{r['tbl_id']} | {r['tbl_nm']} | {r['item_count']} | "
                      f"{axes} | {r['period_count']} |")
        else:
            md.append(f"| {r['org_id']}/{r['tbl_id']} | {r['tbl_nm']} | ✗ | {r['error']} | - |")
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"메타 조회 성공 {ok}/{len(rows)}")
    for r in rows:
        if r["ok"]:
            print(f"  ✓ {r['org_id']}/{r['tbl_id']}  항목{r['item_count']}·축{r['axis_count']}·"
                  f"주기{r['period_count']}  | {r['tbl_nm']}")
        else:
            print(f"  ✗ {r['org_id']}/{r['tbl_id']}  {r['error']}  | {r['tbl_nm']}")
    print(f"\n저장: {OUT_MD.name}, {OUT_JSON.name}")


if __name__ == "__main__":
    main()
