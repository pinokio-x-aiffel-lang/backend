"""메타 테스트셋 30표에 fetch_table_schema 를 돌려 결과를 JSON 으로 저장.

collect_meta_testset.py 로 뽑은 (org_id, tbl_id) 30개가 대상이다.
ITM+PRD 통합 메타(TableSchema)를 asyncio.gather 로 동시 조회한다.
표별 성공/실패를 tests/meta_testset_results.json 에 저장한다.
rate limit 은 공유 client(1000/min)가 보장한다.

    uv run x python tests/fetch_meta_testset.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.kosis import fetch_table_schema

OUT_PATH = Path(__file__).parent / "meta_testset_results.json"

# collect_meta_testset.py 결과(2026-06-09). (org_id, tbl_id, 표명)
META_TEST_TABLES: list[tuple[str, str, str]] = [
    ("101", "DT_1DA7104S", "행정구역(시도)/성별 실업률"),
    ("101", "DT_1DA7107S", "행정구역(시도)/연령별 실업률"),
    ("101", "DT_1DA7102S", "성/연령별 실업률"),
    ("101", "DT_1DA7001S", "성별 경제활동인구 총괄"),
    ("101", "DT_1DA7004S", "행정구역(시도)별 경제활동인구"),
    ("101", "DT_1DA7002S", "연령별 경제활동인구 총괄"),
    ("101", "DT_XNN0004", "합계출산율 - 동북·중앙아시아"),
    ("101", "DT_2KAA207", "합계출산율"),
    ("101", "DT_XNS0004", "합계출산율 - 남부·동남아시아"),
    ("101", "DT_1B83A11", "시도/부부의 혼인종류별 혼인"),
    ("101", "DT_1B8000H", "시도/인구동태건수 및 동태율"),
    ("101", "DT_1B83A24", "시도/시군구별 외국인과의 혼인"),
    ("101", "DT_1B85030", "이혼종류별 외국인과의 이혼"),
    ("101", "DT_1B85026", "미성년자녀수/외국인 남편의 국적별 이혼"),
    ("101", "DT_1B85019", "연령(5세)/이혼종류별 이혼"),
    ("101", "DT_2IFS002", "소비자물가지수"),
    ("101", "DT_2OEEO0121", "소비자물가지수"),
    ("101", "DT_1J22003", "소비자물가지수(2020=100)"),
    ("101", "DT_2KAA202", "부양비 및 노령화지수"),
    ("101", "DT_XNS0011", "부양인구비 및 노령화지수 - 남부·동남아시아"),
    ("101", "DT_XNN0011", "부양인구비 및 노령화지수 - 동북·중앙아시아"),
    ("101", "DT_1B34E07", "사망원인/성/연령별 사망자수, 사망률"),
    ("101", "DT_1B34E18", "특정 사망원인(고의적 자해)(분기별)"),
    ("101", "DT_1B34E19", "시도별 특정 사망원인(고의적 자해)(분기별)"),
    ("101", "DT_1B8000I", "시군구/인구동태건수 및 동태율"),
    ("101", "DT_2UNS0237", "5세 미만 출생 등록 비율"),
    ("101", "DT_XNS0110", "경제성장률(불변가격) - 남부·동남아시아"),
    ("388", "TX_38803_A026", "연도별 전력수급 실적"),
    ("101", "DT_1YL20571", "경제성장률(시도)"),
    ("360", "DT_36005_A003", "항목별 EBSI"),
]


async def _one(org_id: str, tbl_id: str, name: str) -> dict:
    """표 1건 메타 조회 → 결과 레코드. 실패해도 예외 대신 error 필드로 기록."""
    rec: dict = {"org_id": org_id, "tbl_id": tbl_id, "search_name": name}
    try:
        schema = await fetch_table_schema(org_id, tbl_id)
    except Exception as exc:  # noqa: BLE001 — 표별 실패는 결과에 담아 계속
        rec["ok"] = False
        rec["error"] = f"{type(exc).__name__}: {exc}"
        return rec
    rec["ok"] = True
    rec["item_count"] = len(schema.items)
    rec["axis_count"] = schema.axis_count
    rec["period_count"] = len(schema.periods)
    rec["schema"] = schema.to_dict()
    return rec


async def main() -> None:
    records = await asyncio.gather(
        *(_one(org, tbl, nm) for org, tbl, nm in META_TEST_TABLES)
    )
    ok = [r for r in records if r["ok"]]
    fail = [r for r in records if not r["ok"]]

    payload = {
        "summary": {
            "total": len(records),
            "ok": len(ok),
            "fail": len(fail),
            "failed_tables": [(r["org_id"], r["tbl_id"], r["error"]) for r in fail],
        },
        "results": records,
    }
    OUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"총 {len(records)}표  성공 {len(ok)}  실패 {len(fail)}")
    for r in ok:
        print(f"  ✓ {r['org_id']}/{r['tbl_id']}  "
              f"항목 {r['item_count']} · 축 {r['axis_count']} · 주기 {r['period_count']}"
              f"  | {r['search_name']}")
    for r in fail:
        print(f"  ✗ {r['org_id']}/{r['tbl_id']}  {r['error']}  | {r['search_name']}")
    print(f"\n저장: {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
