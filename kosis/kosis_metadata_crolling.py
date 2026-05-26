"""
KOSIS 통계표 메타데이터 수집기
================================

KOSIS 공유서비스(OpenAPI)의 통계자료 getMeta(통계표설명자료) 서비스를 이용하여
하나의 통계표(orgId + tblId)에 대한 구조 메타데이터를 type별로 수집한다.

엔드포인트: https://kosis.kr/openapi/statisticsData.do?method=getMeta
  (긴 조사 설명문을 주는 statisticsExplData.do(통계설명)와는 다른 서비스다.)

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

from __future__ import annotations

import os
import time
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import requests
from dotenv import load_dotenv


# --------------------------------------------------------------------------- #
# 설정
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("kosis_metadata")

# 통계표설명자료(통계표 구조 메타) 엔드포인트.
# 주의: statisticsExplData.do(통계설명, 긴 조사 설명문)와는 다름
# 통계표 구조 메타는 통계자료 서비스의 getMeta 메서드로 받는다.
META_URL = "https://kosis.kr/openapi/statisticsData.do"

META_ITEMS: dict[str, str] = {
    "TBL": "통계표명칭",
    "ORG": "기관명칭",
    "PRD": "수록정보",
    "ITM": "분류항목",
    "CMMT": "주석",
    "UNIT": "단위",
    "SOURCE": "출처",
    "WGT": "가중치",
}


class KosisAPIError(RuntimeError):
    """KOSIS API가 에러 응답(ERR_CODE/ERR_MSG)을 반환했을 때 발생."""


# --------------------------------------------------------------------------- #
# 데이터 클래스
# --------------------------------------------------------------------------- #
@dataclass
class TableMeta:
    """단일 통계표의 메타데이터 묶음."""

    org_id: str
    tbl_id: str
    items: dict[str, Any] = field(default_factory=dict)  # type -> 응답
    errors: dict[str, str] = field(default_factory=dict)  # type -> 에러메시지

    def to_dict(self) -> dict[str, Any]:
        return {
            "orgId": self.org_id,
            "tblId": self.tbl_id,
            "items": self.items,
            "errors": self.errors,
        }


# --------------------------------------------------------------------------- #
# 수집기 본체
# --------------------------------------------------------------------------- #
class KosisMetadataCollector:
    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        timeout: int = 30,
        retries: int = 3,
        sleep_between: float = 0.3,
    ) -> None:
        """
        Parameters
        ----------
        api_key : str | None
            KOSIS 인증키. None이면 .env의 KOSIS_API_KEY를 읽는다.
        timeout : int
            요청 타임아웃(초).
        retries : int
            요청 실패 시 재시도 횟수.
        sleep_between : float
            연속 호출 간 대기 시간(초). KOSIS 호출 제한 완화용.
        """
        if api_key is None:
            load_dotenv()  # 현재 디렉토리 또는 상위의 .env 로드
            api_key = os.getenv("KOSIS_API_KEY")

        if not api_key:
            raise ValueError(
                "API 키가 없습니다. .env 파일에 KOSIS_API_KEY=... 형태로 지정하세요."
            )

        self.api_key = api_key
        self.timeout = timeout
        self.retries = retries
        self.sleep_between = sleep_between
        self.session = requests.Session()

    # ------------------------------------------------------------------ #
    # 저수준 호출
    # ------------------------------------------------------------------ #
    def _request(self, params: dict[str, str]) -> Any:
        """GET 요청 후 JSON 파싱. 에러 응답은 KosisAPIError로 전환."""
        params = {
            "method": "getMeta",
            "apiKey": self.api_key,
            "format": "json",
            "jsonVD": "Y",
            **params,
        }

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(
                    META_URL, params=params, timeout=self.timeout
                )
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, json.JSONDecodeError) as exc:
                last_exc = exc
                wait = self.sleep_between * attempt
                logger.warning(
                    "요청 실패 (%d/%d): %s — %.1fs 후 재시도",
                    attempt,
                    self.retries,
                    exc,
                    wait,
                )
                time.sleep(wait)
                continue

            # KOSIS는 에러 시 dict {"err": ..., "errMsg": ...} 형태로 응답
            if isinstance(data, dict) and ("err" in data or "errMsg" in data):
                raise KosisAPIError(
                    f"{data.get('err', '?')}: {data.get('errMsg', data)}"
                )
            return data

        raise KosisAPIError(f"최대 재시도 초과: {last_exc}")

    # ------------------------------------------------------------------ #
    # 고수준 API
    # ------------------------------------------------------------------ #
    def fetch_meta_item(
        self, org_id: str, tbl_id: str, meta_item: str
    ) -> Any:
        """특정 type 메타 하나를 조회한다 (예: TBL, ITM, UNIT...)."""
        return self._request(
            {"orgId": org_id, "tblId": tbl_id, "type": meta_item}
        )

    def fetch_table(
        self,
        org_id: str,
        tbl_id: str,
        meta_items: Optional[list[str]] = None,
    ) -> TableMeta:
        """
        하나의 통계표에 대해 지정한 메타 항목들을 모두 수집한다.

        meta_items가 None이면 META_ITEMS 전체를 순회한다.
        """
        if meta_items is None:
            meta_items = list(META_ITEMS.keys())

        result = TableMeta(org_id=org_id, tbl_id=tbl_id)
        logger.info("통계표 메타 수집 시작: orgId=%s tblId=%s", org_id, tbl_id)

        for item in meta_items:
            label = META_ITEMS.get(item, item)
            try:
                data = self.fetch_meta_item(org_id, tbl_id, item)
                result.items[item] = data
                logger.info("  ✓ %s (%s)", item, label)
            except KosisAPIError as exc:
                result.errors[item] = str(exc)
                logger.warning("  ✗ %s (%s): %s", item, label, exc)
            time.sleep(self.sleep_between)

        return result

    def fetch_many(
        self,
        tables: list[tuple[str, str]],
        meta_items: Optional[list[str]] = None,
    ) -> list[TableMeta]:
        """
        여러 통계표를 일괄 수집한다.

        tables : [(orgId, tblId), ...]
        """
        results: list[TableMeta] = []
        for i, (org_id, tbl_id) in enumerate(tables, 1):
            logger.info("[%d/%d] 처리 중", i, len(tables))
            results.append(self.fetch_table(org_id, tbl_id, meta_items))
        return results

    # ------------------------------------------------------------------ #
    # 저장 유틸
    # ------------------------------------------------------------------ #
    @staticmethod
    def save_json(results: list[TableMeta], path: str) -> None:
        payload = [r.to_dict() for r in results]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info("JSON 저장 완료: %s (%d개 통계표)", path, len(results))


# --------------------------------------------------------------------------- #
# CLI 진입점
# --------------------------------------------------------------------------- #
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="KOSIS 통계표 메타데이터 수집기"
    )
    parser.add_argument("--org", required=True, help="기관코드 (orgId), 예: 101")
    parser.add_argument(
        "--tbl", required=True, help="통계표ID (tblId), 예: DT_1B42"
    )
    parser.add_argument(
        "--items",
        nargs="*",
        default=None,
        help=f"수집할 type 목록 (기본: 전체). 선택지: {', '.join(META_ITEMS)}",
    )
    parser.add_argument(
        "--out", default="kosis_meta.json", help="출력 JSON 파일 경로"
    )
    args = parser.parse_args()

    collector = KosisMetadataCollector()
    result = collector.fetch_table(args.org, args.tbl, args.items)
    collector.save_json([result], args.out)


if __name__ == "__main__":
    main()
