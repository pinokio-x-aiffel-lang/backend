"""KOSIS metadata 모듈 라이브 테스트 — statisticsData.do?method=getMeta 실행.

완성된 src/kosis 모듈(fetch_table_meta / fetch_meta_item)로 실제 KOSIS getMeta 를
호출해 통계표 구조 메타(TBL/ITM/PRD...)를 받아오는지 검증한다. ITM 메타는 셀 조회에
필요한 itmId/objL 코드의 출처다.

네트워크 + KOSIS_API_KEY(.env) 필요. 키가 없으면 전체 skip.

실행:
    uv run pytest tests/test_kosis_module.py -v     # 테스트로
    uv run python tests/test_kosis_module.py        # 스크립트로(상세 출력)
    uv run python tests/test_kosis_module.py 101 DT_1B8000F   # 다른 표로

대상 모듈: src.kosis (fetch_table_meta / fetch_meta_item)
작성자: leeaain2027 <leeaain2027@gmail.com>
작성일: 2026-06-06
"""
from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from src.kosis import META_ITEMS, TableMeta, fetch_meta_item, fetch_table_meta

load_dotenv()

# 검증용 통계표: 행정구역(시군구)별, 성별 인구수 (통계청)
ORG_ID = "101"
TBL_ID = "DT_1B040A3"

pytestmark = pytest.mark.skipif(
    not os.getenv("KOSIS_API_KEY"),
    reason="KOSIS_API_KEY 가 .env 에 없어 live getMeta 테스트를 건너뜀",
)


def test_fetch_meta_item_itm():
    """단일 type(ITM) getMeta → 항목/분류축 코드 list."""
    rows = fetch_meta_item(ORG_ID, TBL_ID, "ITM")
    assert isinstance(rows, list) and rows, "ITM 메타가 비어 있음"
    sample = rows[0]
    assert "ITM_ID" in sample and "ITM_NM" in sample
    # 셀 좌표 코드의 출처: ITM_ID(항목 코드)가 들어 있어야 한다
    assert any(r.get("ITM_ID") for r in rows)


def test_fetch_table_meta_full():
    """여러 type 일괄 getMeta → TableMeta(items/errors)."""
    meta = fetch_table_meta(ORG_ID, TBL_ID, meta_types=["TBL", "ITM", "PRD"])
    assert isinstance(meta, TableMeta)
    assert meta.org_id == ORG_ID and meta.tbl_id == TBL_ID
    assert "TBL" in meta.items, "표명(TBL) 메타가 안 잡힘"
    assert "ITM" in meta.items, "항목(ITM) 메타가 안 잡힘"
    itm = meta.items["ITM"]
    assert isinstance(itm, list) and itm


def test_bad_table_records_error():
    """존재하지 않는 tblId → 실패가 errors 에 기록되고 raise 하지 않는다."""
    meta = fetch_table_meta(ORG_ID, "DT_DOES_NOT_EXIST", meta_types=["ITM"])
    assert isinstance(meta, TableMeta)
    # 한 type 실패가 전체를 막지 않아야 한다 (errors 에 기록 또는 빈 결과)
    assert "ITM" in meta.errors or not meta.items.get("ITM")


if __name__ == "__main__":
    # 스크립트 실행: 사람이 보기 좋은 상세 출력
    import sys
    from collections import Counter

    org = sys.argv[1] if len(sys.argv) > 1 else ORG_ID
    tbl = sys.argv[2] if len(sys.argv) > 2 else TBL_ID

    print(f"getMeta: orgId={org} tblId={tbl}  (types={list(META_ITEMS)})")
    meta = fetch_table_meta(org, tbl)
    print(f"  ✓ items : {list(meta.items)}")
    print(f"  ✗ errors: {list(meta.errors)}")

    tbl_meta = meta.items.get("TBL")
    if isinstance(tbl_meta, list) and tbl_meta:
        print(f"  표명: {tbl_meta[0].get('TBL_NM')}")

    itm = meta.items.get("ITM")
    if isinstance(itm, list):
        axes = Counter(r.get("OBJ_NM") for r in itm)
        print(f"  ITM {len(itm)}행, 축별 분포: {dict(axes)}")
        items = [
            (r.get("ITM_ID"), r.get("ITM_NM"))
            for r in itm
            if r.get("OBJ_NM") == "항목"
        ][:5]
        print(f"  항목(itmId) 샘플: {items}")
