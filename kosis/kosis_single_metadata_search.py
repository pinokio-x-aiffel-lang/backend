"""KOSIS 단일 통계표 메타데이터 조회 (CLI)

테이블ID(tblId)를 입력받아 통계표 구조 메타데이터(getMeta)를 type별로 조회/출력한다.
조회 로직은 `src/kosis/meta.py`(fetch_table_meta)를 사용한다.

사용 예:
    uv run python kosis/kosis_single_metadata_search.py "DT_1B42" --org 101

API 키는 프로젝트 루트의 .env 에서 읽는다.
    KOSIS_API_KEY=발급받은_인증키
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# src/ import 위해 프로젝트 루트를 sys.path 에 추가
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from src.kosis import fetch_table_meta  # noqa: E402  (sys.path 조작 후 import)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="KOSIS 테이블ID로 통계표 메타데이터 조회"
    )
    parser.add_argument("tbl_id", help="통계표ID (tblId), 예: DT_1B42")
    parser.add_argument(
        "--org", default="101", help="기관코드 (orgId), 기본값 101(통계청)"
    )
    args = parser.parse_args()

    meta = fetch_table_meta(args.org, args.tbl_id)
    print(json.dumps(meta.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
