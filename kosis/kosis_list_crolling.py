"""
KOSIS 통계목록 순회 수집기
============================

KOSIS 공유서비스(OpenAPI)의 "통계목록" 서비스(statisticsList.do)를 이용하여
분류 트리를 재귀적으로 끝까지 순회하면서, 말단 통계표의 식별자
(orgId, tblId)와 통계표명을 모두 수집한다.

통계목록 API의 동작:
    - vwCd(서비스뷰) + parentListId(시작 목록ID)를 주면
      해당 노드의 "바로 아래 자식"만 반환한다.
    - 응답 항목이 LIST_ID 를 가지면  -> 중간 목록(폴더). 더 내려가야 함.
    - 응답 항목이 TBL_ID  를 가지면  -> 말단 통계표(leaf). 수집 대상.

따라서 전체를 얻으려면 LIST_ID가 나올 때마다 그 ID를 다음 parentListId로
넣어 다시 호출하는 트리 순회가 필요하다.

이 모듈은 모든 vwCd 에 대해 트리를 순회하며, 중간에 끊겨도 이어받을 수
있도록 방문한 (vwCd, listId)를 체크포인트 파일에 기록한다.

API 키는 프로젝트 루트의 .env 파일에서 읽는다.
    KOSIS_API_KEY=발급받은_인증키
"""

from __future__ import annotations

import os
import csv
import time
import json
import logging
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Iterable

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
logger = logging.getLogger("kosis_list")

# 통계목록 서비스 엔드포인트
LIST_URL = "https://kosis.kr/openapi/statisticsList.do"

# 서비스뷰 코드 (KOSIS 개발가이드 기준). 키=코드, 값=설명
VIEW_CODES: dict[str, str] = {
    "MT_ZTITLE": "국내통계 주제별",
    "MT_OTITLE": "국내통계 기관별",
    "MT_GTITLE01": "e-지방지표(주제별)",
    "MT_GTITLE02": "e-지방지표(지역별)",
    "MT_CHOSUN_TITLE": "광복이전통계(1908~1943)",
    "MT_HANKUK_TITLE": "대한민국통계연감",
    "MT_STOP_TITLE": "작성중지통계",
    "MT_RTITLE": "국제통계",
    "MT_BUKHAN": "북한통계",
    "MT_TM1_TITLE": "대상별통계",
    "MT_TM2_TITLE": "이슈별통계",
    "MT_ETITLE": "영문 KOSIS",
}

# 루트 호출 시 parentListId. KOSIS는 빈 문자열이면 최상위 목록을 반환한다.
ROOT_PARENT_ID = ""


class KosisAPIError(RuntimeError):
    """KOSIS API가 에러 응답을 반환했을 때 발생."""


# --------------------------------------------------------------------------- #
# 데이터 클래스
# --------------------------------------------------------------------------- #
@dataclass
class StatTable:
    """순회 중 발견한 말단 통계표 한 건."""

    vw_cd: str
    org_id: str
    tbl_id: str
    tbl_nm: str
    list_id: str = ""  # 이 통계표가 속한 부모 목록ID

    def key(self) -> tuple[str, str]:
        return (self.org_id, self.tbl_id)


# --------------------------------------------------------------------------- #
# 순회 수집기
# --------------------------------------------------------------------------- #
class KosisListCrawler:
    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        timeout: int = 30,
        retries: int = 3,
        sleep_between: float = 0.2,
        checkpoint_path: Optional[str] = None,
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
            연속 호출 간 대기 시간(초).
        checkpoint_path : str | None
            방문 완료한 목록 노드를 기록할 파일 경로. 지정하면 재실행 시
            이미 방문한 노드를 건너뛰어 이어받기가 가능하다.
        """
        if api_key is None:
            load_dotenv()
            api_key = os.getenv("KOSIS_API_KEY")
        if not api_key:
            raise ValueError(
                "API 키가 없습니다. .env 파일에 KOSIS_API_KEY=... 를 지정하세요."
            )

        self.api_key = api_key
        self.timeout = timeout
        self.retries = retries
        self.sleep_between = sleep_between
        self.checkpoint_path = checkpoint_path
        self.session = requests.Session()

        # 방문 완료한 (vwCd, listId) 집합 — 무한루프/중복 방지
        self._visited: set[tuple[str, str]] = set()
        if checkpoint_path and os.path.exists(checkpoint_path):
            self._load_checkpoint()

    # ------------------------------------------------------------------ #
    # 체크포인트
    # ------------------------------------------------------------------ #
    def _load_checkpoint(self) -> None:
        with open(self.checkpoint_path, encoding="utf-8") as f:
            for line in f:
                # 개행만 제거. rstrip()/strip()은 빈 listId(루트, 뒤쪽 탭)를
                # 지워버려 (vwCd, "") 복원이 깨지므로 사용하지 않는다.
                line = line.rstrip("\n").rstrip("\r")
                if "\t" in line:
                    vw, lid = line.split("\t", 1)
                    self._visited.add((vw, lid))
        logger.info("체크포인트 로드: %d개 노드 이미 방문", len(self._visited))

    def _mark_visited(self, vw_cd: str, list_id: str) -> None:
        self._visited.add((vw_cd, list_id))
        if self.checkpoint_path:
            with open(self.checkpoint_path, "a", encoding="utf-8") as f:
                f.write(f"{vw_cd}\t{list_id}\n")

    # ------------------------------------------------------------------ #
    # 저수준 호출
    # ------------------------------------------------------------------ #
    def _request(self, vw_cd: str, parent_list_id: str) -> list[dict[str, Any]]:
        """통계목록 API를 한 번 호출해 자식 노드 리스트를 반환."""
        params = {
            "method": "getList",
            "apiKey": self.api_key,
            "format": "json",
            "jsonVD": "Y",
            "vwCd": vw_cd,
            "parentListId": parent_list_id,
        }

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(
                    LIST_URL, params=params, timeout=self.timeout
                )
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, json.JSONDecodeError) as exc:
                last_exc = exc
                wait = self.sleep_between * attempt * 2
                logger.warning(
                    "요청 실패 (%d/%d) vwCd=%s parent=%s: %s — %.1fs 후 재시도",
                    attempt, self.retries, vw_cd, parent_list_id, exc, wait,
                )
                time.sleep(wait)
                continue

            # 에러 응답 처리: KOSIS는 dict {"err":..,"errMsg":..} 로 응답
            if isinstance(data, dict) and ("err" in data or "errMsg" in data):
                raise KosisAPIError(
                    f"{data.get('err', '?')}: {data.get('errMsg', data)}"
                )
            # 정상 응답은 항상 리스트. 혹시 단일 dict면 리스트로 감싼다.
            if isinstance(data, dict):
                return [data]
            return data or []

        raise KosisAPIError(f"최대 재시도 초과: {last_exc}")

    # ------------------------------------------------------------------ #
    # 트리 순회 (단일 vwCd)
    # ------------------------------------------------------------------ #
    def crawl_view(
        self,
        vw_cd: str,
        *,
        root_parent_id: str = ROOT_PARENT_ID,
        max_nodes: Optional[int] = None,
        max_tables: Optional[int] = None,
        csv_path: Optional[str] = None,
        flush_every: int = 100,
    ) -> list[StatTable]:
        """
        하나의 vwCd 트리를 너비우선(BFS)으로 끝까지 순회하여
        말단 통계표를 모두 수집한다.

        root_parent_id : 순회 시작 목록ID. 기본은 최상위("").
            특정 주제(예: '인구'=A)만 받으려면 그 LIST_ID를 지정한다.
        max_nodes : 방문할 목록 노드 수 상한(테스트/부분수집용). None이면 무제한.
        max_tables : 수집할 통계표 수 상한. 도달 즉시 더 조회하지 않고 중단.
        csv_path : 지정하면 통계표를 발견하는 즉시 이 CSV에 기록하고,
            flush_every개마다 디스크에 flush한다(중간에 끊겨도 결과 보존).
        flush_every : 디스크 flush 주기(통계표 개수). 기본 100.
        """
        tables: list[StatTable] = []
        seen_tables: set[tuple[str, str]] = set()
        queue: deque[str] = deque([root_parent_id])
        node_count = 0

        # 중간 저장용 CSV (지정 시): 헤더 먼저 쓰고, flush_every마다 flush
        csv_file = None
        csv_writer = None
        since_flush = 0
        if csv_path:
            csv_file = open(csv_path, "w", encoding="utf-8-sig", newline="")
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(["vwCd", "orgId", "tblId", "tblNm", "listId"])
            csv_file.flush()

        logger.info("[%s] %s 순회 시작", vw_cd, VIEW_CODES.get(vw_cd, ""))

        try:
            while queue:
                list_id = queue.popleft()
                if (vw_cd, list_id) in self._visited:
                    continue
                if max_nodes is not None and node_count >= max_nodes:
                    logger.info("[%s] max_nodes(%d) 도달 — 중단", vw_cd, max_nodes)
                    break
                if max_tables is not None and len(tables) >= max_tables:
                    logger.info("[%s] max_tables(%d) 도달 — 중단", vw_cd, max_tables)
                    break

                try:
                    children = self._request(vw_cd, list_id)
                except KosisAPIError as exc:
                    logger.warning("[%s] 노드 '%s' 조회 실패: %s", vw_cd, list_id, exc)
                    self._mark_visited(vw_cd, list_id)
                    time.sleep(self.sleep_between)
                    continue

                for node in children:
                    # 말단 통계표: TBL_ID 보유
                    if node.get("TBL_ID"):
                        t = StatTable(
                            vw_cd=vw_cd,
                            org_id=str(node.get("ORG_ID", "")),
                            tbl_id=str(node["TBL_ID"]),
                            tbl_nm=str(node.get("TBL_NM", "")),
                            list_id=list_id,
                        )
                        if t.key() not in seen_tables:
                            seen_tables.add(t.key())
                            tables.append(t)
                            if csv_writer is not None:
                                csv_writer.writerow(
                                    [t.vw_cd, t.org_id, t.tbl_id, t.tbl_nm, t.list_id]
                                )
                                since_flush += 1
                                if since_flush >= flush_every:
                                    csv_file.flush()
                                    since_flush = 0
                                    logger.info(
                                        "[%s] 중간 저장: 통계표 %d개 → %s",
                                        vw_cd, len(tables), csv_path,
                                    )
                            if max_tables is not None and len(tables) >= max_tables:
                                break  # 상한 도달 — 남은 자식 처리 중단
                    # 중간 목록: LIST_ID 보유 -> 큐에 추가해 더 내려간다
                    elif node.get("LIST_ID"):
                        child_id = str(node["LIST_ID"])
                        if (vw_cd, child_id) not in self._visited:
                            queue.append(child_id)

                self._mark_visited(vw_cd, list_id)
                node_count += 1
                if node_count % 50 == 0:
                    logger.info(
                        "[%s] 진행: 노드 %d개 방문, 통계표 %d개 누적",
                        vw_cd, node_count, len(tables),
                    )
                time.sleep(self.sleep_between)
        finally:
            if csv_file is not None:
                csv_file.flush()
                csv_file.close()

        logger.info(
            "[%s] 순회 완료: 노드 %d개, 통계표 %d개", vw_cd, node_count, len(tables)
        )
        return tables

    # ------------------------------------------------------------------ #
    # 전체 vwCd 순회
    # ------------------------------------------------------------------ #
    def crawl_all(
        self,
        view_codes: Optional[Iterable[str]] = None,
        *,
        max_nodes_per_view: Optional[int] = None,
        root_parent_id: str = ROOT_PARENT_ID,
        max_tables_per_view: Optional[int] = None,
        csv_path: Optional[str] = None,
        flush_every: int = 100,
    ) -> list[StatTable]:
        """
        지정한 vwCd들(기본: VIEW_CODES 전체)을 순회하여 모든 통계표를 수집한다.
        뷰가 달라도 같은 (orgId, tblId)는 한 번만 담는다.

        root_parent_id : 순회 시작 목록ID. 기본은 최상위("").
        max_tables_per_view : 뷰별 수집 통계표 상한. 도달 시 중단.
        csv_path : 중간 저장 CSV 경로. 뷰가 1개일 때만 적용한다(여러 뷰면
            뷰마다 파일을 덮어써 충돌하므로, 그 경우 최종 save_csv만 사용).
        """
        if view_codes is None:
            view_codes = list(VIEW_CODES.keys())
        view_codes = list(view_codes)

        # 중간 저장은 단일 뷰 순회에서만 의미가 있다.
        incremental_csv = csv_path if len(view_codes) == 1 else None
        if csv_path and incremental_csv is None:
            logger.warning(
                "중간 저장(csv_path)은 단일 뷰에서만 적용됩니다. "
                "여러 뷰(%d개)라 중간 저장을 건너뛰고 최종 저장만 합니다.",
                len(view_codes),
            )

        all_tables: list[StatTable] = []
        global_seen: set[tuple[str, str]] = set()

        for vw_cd in view_codes:
            view_tables = self.crawl_view(
                vw_cd,
                root_parent_id=root_parent_id,
                max_nodes=max_nodes_per_view,
                max_tables=max_tables_per_view,
                csv_path=incremental_csv,
                flush_every=flush_every,
            )
            for t in view_tables:
                if t.key() not in global_seen:
                    global_seen.add(t.key())
                    all_tables.append(t)

        logger.info(
            "전체 순회 완료: 뷰 %d개, 고유 통계표 %d개",
            len(list(view_codes)), len(all_tables),
        )
        return all_tables

    # ------------------------------------------------------------------ #
    # 저장 유틸
    # ------------------------------------------------------------------ #
    @staticmethod
    def save_csv(tables: list[StatTable], path: str) -> None:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["vwCd", "orgId", "tblId", "tblNm", "listId"])
            for t in tables:
                writer.writerow([t.vw_cd, t.org_id, t.tbl_id, t.tbl_nm, t.list_id])
        logger.info("CSV 저장 완료: %s (%d건)", path, len(tables))

    @staticmethod
    def save_json(tables: list[StatTable], path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump([asdict(t) for t in tables], f, ensure_ascii=False, indent=2)
        logger.info("JSON 저장 완료: %s (%d건)", path, len(tables))


# --------------------------------------------------------------------------- #
# CLI 진입점
# --------------------------------------------------------------------------- #
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="KOSIS 통계목록 전체 순회 → tblId 목록 수집"
    )
    parser.add_argument(
        "--views",
        nargs="*",
        default=["MT_ZTITLE"],
        help=f"순회할 vwCd 목록 (기본: MT_ZTITLE). 선택지: {', '.join(VIEW_CODES)}",
    )
    parser.add_argument(
        "--parent",
        default="A",
        help="순회 시작 목록ID. 기본 'A'(인구). 최상위부터 받으려면 \"\" 지정.",
    )
    parser.add_argument(
        "--max-tables",
        type=int,
        default=5000,
        help="뷰별 수집 통계표 상한. 기본 5000. 도달 즉시 중단.",
    )
    parser.add_argument(
        "--max-nodes",
        type=int,
        default=None,
        help="뷰별 방문 목록 노드 수 상한. 기본 무제한(통계표 수로만 제한).",
    )
    parser.add_argument(
        "--checkpoint",
        default="kosis_list.checkpoint",
        help="이어받기용 체크포인트 파일 경로",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="실행 전 체크포인트 파일을 삭제하고 처음부터 다시 순회한다.",
    )
    parser.add_argument("--csv", default="result_.csv", help="출력 CSV 경로")
    parser.add_argument(
        "--flush-every",
        type=int,
        default=100,
        help="중간 저장 주기(통계표 개수). 기본 100. 단일 뷰 순회에서만 적용.",
    )
    parser.add_argument("--json", default=None, help="출력 JSON 경로(선택)")
    args = parser.parse_args()

    if args.reset and os.path.exists(args.checkpoint):
        os.remove(args.checkpoint)
        logger.info("체크포인트 삭제: %s — 처음부터 순회", args.checkpoint)

    crawler = KosisListCrawler(checkpoint_path=args.checkpoint)
    tables = crawler.crawl_all(
        view_codes=args.views,
        max_nodes_per_view=args.max_nodes,
        root_parent_id=args.parent,
        max_tables_per_view=args.max_tables,
        csv_path=args.csv,
        flush_every=args.flush_every,
    )
    crawler.save_csv(tables, args.csv)
    if args.json:
        crawler.save_json(tables, args.json)


if __name__ == "__main__":
    main()
