"""[4-5] KOSIS 키워드 검색 → 상위 N개 통계표 메타데이터 조회 → metadatas.json 저장.

[4] search_tables(키워드)로 상위 N개 통계표를 찾고, [5] 각 표마다
fetch_table_metadata(orgId, tblId)로 ITM(항목·분류축)+PRD(주기) 메타를 받아온다.
분류축은 OBJ_ID_SN 순이라 axes[0]=objL1, axes[1]=objL2 … 로 라벨을 붙여 출력한다.
메타는 길어서 콘솔엔 요약만 찍고 전체는 tests/results/metadatas.json 에 저장.
키는 `uv run x` 가 주입.

    uv run x python tests/260611_4-5_kosis-search-meta_leeaain.py "경제성장률"
    uv run x python tests/260611_4-5_kosis-search-meta_leeaain.py "경제성장률" 5   # 상위 5개
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.kosis import KosisError, fetch_table_metadata, search_tables

load_dotenv()

RESULTS_DIR = Path(__file__).parent / "results"  # 저장 파일명은 키워드별(metadatas_<키워드>.json)


async def _meta_for(hit) -> dict:
    """검색 결과 1건 → 메타데이터 dict(축에 objL 라벨 부여). 실패해도 죽지 않게 흡수."""
    try:
        # fetch_table_metadata 는 동기(ThreadPoolExecutor 내부) → to_thread 로 동시 실행.
        meta = await asyncio.to_thread(fetch_table_metadata, hit.org_id, hit.tbl_id)
    except (KosisError, ValueError) as e:
        return {"tbl_nm": hit.tbl_nm, "orgId": hit.org_id, "tblId": hit.tbl_id,
                "error": str(e)}

    d = meta.to_dict()
    d["tbl_nm"] = hit.tbl_nm  # 메타 응답엔 표명이 없어 검색 결과로 채움
    d["stat_nm"], d["org_nm"], d["prd_de"] = hit.stat_nm, hit.org_nm, hit.prd_de
    # 분류축에 objL 좌표 라벨(축 순서 = objL 번호). axes 는 이미 OBJ_ID_SN 순.
    for i, ax in enumerate(d["axes"], 1):
        ax["objL"] = f"objL{i}"
    return d


async def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print('사용법: uv run x python tests/260611_4-5_kosis-search-meta_leeaain.py "키워드" [개수]')
        sys.exit(1)

    keyword = sys.argv[1].strip()
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    try:
        hits = search_tables(keyword, top_n=top_n)
    except (KosisError, ValueError) as e:
        print(f"검색 실패: {e}")
        sys.exit(1)

    print(f'\n키워드 "{keyword}" → 통계표 {len(hits)}건, 메타 조회 중...\n')
    metas = await asyncio.gather(*(_meta_for(h) for h in hits))  # 동시 조회

    for i, m in enumerate(metas, 1):
        print(f"[{i:2}] {m['tbl_nm']}  (orgId={m['orgId']} tblId={m['tblId']})")
        if "error" in m:
            print(f"     메타 조회 실패: {m['error']}")
            continue
        items = ", ".join(it["itm_nm"] for it in m["items"]) or "—"
        print(f"     항목(ITM): {items}")
        for ax in m["axes"]:
            head = ", ".join(nm for _, nm in ax["values"][:5])
            more = " …" if len(ax["values"]) > 5 else ""
            print(f"     {ax['objL']} = {ax['name']} ({len(ax['values'])}개): {head}{more}")
        if not m["axes"]:
            print("     분류축 없음(objL 없음)")
        periods = ", ".join(f"{p['se_label']}({p['start']}~{p['end']})" for p in m["periods"])
        print(f"     주기(PRD): {periods or '—'}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out_json = RESULTS_DIR / f"metadatas_{keyword}.json"  # 키워드별 파일
    out_json.write_text(
        json.dumps({"keyword": keyword, "count": len(metas), "tables": metas},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n전체 메타 저장: {out_json.relative_to(Path.cwd())}")


if __name__ == "__main__":
    asyncio.run(main())
