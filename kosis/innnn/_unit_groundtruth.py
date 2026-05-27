"""세 케이스 표의 실제 데이터(statisticsParameterData)를 받아 UNIT_NM 존재 확인.

UNIT type 메타 호출이 비어있는 표가:
- 진짜 단위가 없는 건지
- KOSIS API의 UNIT 엔드포인트가 sparse 한 건지 (실 데이터엔 있음)
를 결판낸다.
"""
from __future__ import annotations

import json
import os
import sys

import httpx
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()
API_KEY = os.getenv("KOSIS_API_KEY")

DATA_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

# 스모크 테스트 결과 기준 세 케이스
CASES = [
    {
        "label": "UNIT type X + ITM에 UNIT_NM O",
        "org_id": "142",
        "tbl_id": "DT_A10032_C",
        # 우리 jsonl의 PRD: 년 / 2011~2011
        "params": {"prdSe": "Y", "startPrdDe": "2011", "endPrdDe": "2011"},
    },
    {
        "label": "UNIT type X + ITM에 UNIT_NM X",
        "org_id": "142",
        "tbl_id": "DT_19051",
        # PRD 모르므로 광범위 시도. KOSIS 가 자동으로 받아들이는지 보자.
        "params": {"prdSe": "Y", "startPrdDe": "1900", "endPrdDe": "2025"},
    },
    {
        "label": "UNIT type O",
        "org_id": "778",
        "tbl_id": "DT_77801_P000002",
        "params": {"prdSe": "Y", "startPrdDe": "1900", "endPrdDe": "2025"},
    },
]


def fetch(case: dict) -> None:
    params = {
        "method": "getList",
        "apiKey": API_KEY,
        "format": "json",
        "jsonVD": "Y",
        "orgId": case["org_id"],
        "tblId": case["tbl_id"],
        "objL1": "ALL",
        "itmId": "ALL",
        **case["params"],
    }
    print(f"\n=== {case['label']} ===")
    print(f"  org={case['org_id']} tbl={case['tbl_id']}")
    try:
        r = httpx.get(DATA_URL, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  요청 실패: {e}")
        return

    if isinstance(data, dict) and "err" in data:
        print(f"  API 에러: {data}")
        return
    if not data:
        print("  응답 비어있음")
        return

    if isinstance(data, dict):
        data = [data]

    print(f"  레코드 수: {len(data)}")
    # 첫 레코드의 모든 필드와, UNIT 관련 필드 강조
    first = data[0]
    unit_fields = {k: v for k, v in first.items() if "UNIT" in k.upper()}
    print(f"  첫 레코드의 UNIT 관련 필드: {unit_fields if unit_fields else '없음'}")
    # 핵심 필드만 첫 3 레코드 미리보기
    print("  첫 3 레코드 미리보기:")
    for rec in data[:3]:
        slim = {
            k: v for k, v in rec.items()
            if k in ("PRD_DE", "C1_NM", "ITM_NM", "DT", "UNIT_NM")
        }
        print(f"    {slim}")


if __name__ == "__main__":
    if not API_KEY:
        raise SystemExit("KOSIS_API_KEY 없음 (.env 확인)")
    for c in CASES:
        fetch(c)
