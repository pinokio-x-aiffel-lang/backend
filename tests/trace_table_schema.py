"""fetch_table_schema(ITM+PRD 병렬→TableSchema) 라이브 점검.

알려진 표 3종(1축·다축·월간)에 대해 items/axes/periods 가 제대로 파싱되는지 출력.
KOSIS_API_KEY 필요 → `uv run x python tests/trace_table_schema.py`.
"""
from __future__ import annotations

import asyncio

from src.kosis import fetch_table_schema

# (org_id, tbl_id, 설명)
TABLES = [
    ("101", "DT_1YL20531E", "1축: 행정구역별(연간)"),
    ("101", "DT_1DE9046S", "다축: 연령별 경제활동상태(연간)"),
    ("101", "DT_1DA7004S", "성별/연령별 실업률(월간)"),
]


async def _show(org_id: str, tbl_id: str, desc: str) -> None:
    print(f"\n{'='*70}\n[{org_id}/{tbl_id}] {desc}")
    schema = await fetch_table_schema(org_id, tbl_id)

    print(f"  항목(items) {len(schema.items)}개:")
    for it in schema.items[:10]:
        print(f"    - {it.itm_id}  {it.itm_nm}  ({it.unit})")
    if len(schema.items) > 10:
        print(f"    …외 {len(schema.items) - 10}개")

    print(f"  분류축(axes) {schema.axis_count}개 (OBJ_ID_SN 순):")
    for ax in schema.axes:
        sample = ", ".join(nm for _id, nm in ax.values[:6])
        more = f" …외 {len(ax.values) - 6}개" if len(ax.values) > 6 else ""
        print(f"    - OBJ {ax.obj_id} sn={ax.sn} '{ax.name}' [{len(ax.values)}값]"
              f": {sample}{more}")

    print(f"  주기(periods) {len(schema.periods)}개:")
    for p in schema.periods:
        print(f"    - {p.se_label!r}→{p.se_code!r} fmt={p.fmt!r} "
              f"범위 {p.start}~{p.end}")


async def main() -> None:
    for org_id, tbl_id, desc in TABLES:
        try:
            await _show(org_id, tbl_id, desc)
        except Exception as exc:  # noqa: BLE001 — 진단 스크립트, 표별 실패 표시만
            print(f"  ✗ 실패: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
