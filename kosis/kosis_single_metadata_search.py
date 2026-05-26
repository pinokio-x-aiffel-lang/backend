"""
KOSIS 단일 통계표 메타데이터 조회 (CLI)
=======================================

테이블ID(tblId)를 입력받아 해당 통계표의 메타데이터를 조회/출력한다.

사용 예:
    uv run python kosis_single_metadata_search.py "DT_1B42" --top 50

주의:
    - KOSIS getMeta API는 orgId도 필요하다. 기본값은 101(통계청)이며,
      다른 기관 통계표는 --org 로 지정한다.
    - --top 인자는 (키워드 검색용 호환을 위해) 받기만 하고 무시한다.

수집 항목 (getMeta의 type):
    - TBL    : 통계표명칭
    - ORG    : 기관명칭
    - PRD    : 수록정보 (수록기간 등)
    - ITM    : 분류/항목 정보
    - CMMT   : 주석
    - UNIT   : 단위
    - SOURCE : 출처
    - WGT    : 가중치

API 키는 프로젝트 루트의 .env 파일에서 읽는다.
    KOSIS_API_KEY=발급받은_인증키
"""

import argparse
import json

from kosis_metadata_crolling import KosisMetadataCollector


def main() -> None:
    parser = argparse.ArgumentParser(
        description="KOSIS 테이블ID로 통계표 메타데이터 조회"
    )
    parser.add_argument("tbl_id", help="통계표ID (tblId), 예: DT_1B42")
    parser.add_argument(
        "--org", default="101", help="기관코드 (orgId), 기본값 101(통계청)"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="(무시됨) 키워드 검색용 인자 호환을 위해 받기만 한다",
    )
    args = parser.parse_args()

    collector = KosisMetadataCollector()
    result = collector.fetch_table(args.org, args.tbl_id)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
