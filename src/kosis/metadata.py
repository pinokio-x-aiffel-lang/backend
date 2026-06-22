"""KOSIS 통계표 구조 메타데이터(statisticsData.do?method=getMeta).

통계표(orgId+tblId)의 항목(ITM)·분류축(OBJ)·시점(PRD)·단위 등 구조 메타를
type별로 조회한다. 셀 조회(cell.fetch_cell)에 필요한 itmId/objL/prdSe **코드의 출처**.
(긴 조사 설명문을 주는 statisticsExplData.do(통계설명)와는 다른 서비스.)

공유 HTTP 레이어(client.kosis_get)를 거쳐 Session·재시도·rate limit·jsonVD=Y 가
적용된다. getMeta 는 type 1개당 1종만 반환(type=ALL 없음)하므로 필요한 type 만
순회 조회한다. type별 실패(KosisError)는 TableMeta.errors 에 모아 두고 계속한다.
"""
from __future__ import annotations

import contextvars
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Optional

from src.kosis.client import META_URL, KosisError, kosis_get, resolve_api_key

logger = logging.getLogger("kosis")

# getMeta type 코드 → 한글 라벨. WGT(가중치) 포함 8종.
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


@dataclass
class TableMeta:
    """단일 통계표의 구조 메타데이터 묶음.

    items  : type → getMeta 응답(list/dict). 성공한 type 만 담긴다.
    errors : type → 에러 메시지. KOSIS 가 빈/오류 응답을 준 type.
    """

    org_id: str
    tbl_id: str
    items: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "orgId": self.org_id,
            "tblId": self.tbl_id,
            "items": self.items,
            "errors": self.errors,
        }


def fetch_meta_item(
    org_id: str,
    tbl_id: str,
    meta_type: str,
    api_key: Optional[str] = None,
) -> Any:
    """getMeta type 하나를 조회한다 (예: ITM, PRD, UNIT...).

    Raises:
        KosisError: KOSIS 가 빈/오류 응답(err/errMsg)을 준 경우.
        ValueError: API 키가 없는 경우.
    """
    return kosis_get(
        META_URL,
        {
            "method": "getMeta",
            "apiKey": resolve_api_key(api_key),
            "type": meta_type,
            "orgId": org_id,
            "tblId": tbl_id,
        },
    )


def fetch_table_meta(
    org_id: str,
    tbl_id: str,
    api_key: Optional[str] = None,
    *,
    meta_types: Optional[list[str]] = None,
) -> TableMeta:
    """통계표 1건의 메타를 type별로 수집한다. type별 실패는 errors 에 기록하고 계속.

    meta_types=None 이면 META_ITEMS 전체(8종)를 순회한다.

    Raises:
        ValueError: API 키가 없는 경우(키는 1회만 검증).
    """
    key = resolve_api_key(api_key)  # 키를 미리 한 번 검증/확보
    types = meta_types or list(META_ITEMS)
    result = TableMeta(org_id=org_id, tbl_id=tbl_id)

    t0 = time.perf_counter()
    for meta_type in types:
        try:
            result.items[meta_type] = fetch_meta_item(org_id, tbl_id, meta_type, key)
        except KosisError as exc:
            result.errors[meta_type] = str(exc)
    logger.info(
        "KOSIS 메타 orgId=%s tblId=%s: %d/%d type 성공 (%.3fs)",
        org_id, tbl_id, len(result.items), len(types), time.perf_counter() - t0,
    )
    return result


# ── ITM+PRD 통합 파싱(TableMetadata) ──────────────────────────────────────────
# 값 조회에 필요한 두 메타(ITM=항목·분류축, PRD=수록주기)를 함께 받아 한 구조체로
# 파싱한다. 원시 getMeta 응답(평평한 dict 리스트)의 KOSIS 잡스러움(항목·축 혼재,
# 알파벳 OBJ_ID 비순차, 라벨↔코드 불일치)을 흡수해 downstream(map_claim_to_cell/cell)이
# 표별 가정 없이 meta.items / meta.axes / meta.periods 로 읽게 한다.

# PRD_SE 라벨(메타) → 요청 prdSe 코드. (메모리 kosis-prdse-three-representations)
_PRD_SE_CODE: dict[str, str] = {
    "년": "Y", "분기": "Q", "반기": "H", "월": "M", "일": "D",
}
# prdSe 코드 → 요청 시점 형식 힌트. Y/M/Q 는 이 세션에서 실측 확인,
# H(반기 01~02)·D(YYYYMMDD)는 KOSIS 표준(미실측).
_PRD_FMT: dict[str, str] = {
    "Y": "YYYY", "H": "YYYYHH", "Q": "YYYYQQ", "M": "YYYYMM", "D": "YYYYMMDD",
}


@dataclass(frozen=True)
class Item:
    """통계표 항목(getMeta ITM 의 OBJ_ID='ITEM'). 값 조회 itmId 의 출처."""

    itm_id: str
    itm_nm: str
    unit: str = ""


@dataclass(frozen=True)
class Axis:
    """분류축(getMeta ITM 의 OBJ_ID != 'ITEM'). objL 코드의 출처.

    values: [(코드, 이름)]. 정렬·매칭 키는 코드(ITM_ID)다.
    """

    obj_id: str                       # 'A','B','G'... (알파벳이 순차가 아닐 수 있음)
    sn: int                           # OBJ_ID_SN — 진짜 축 순서(=C1,C2… 대응). 정렬 키.
    name: str                         # OBJ_NM, 예 '시도별'
    values: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class Period:
    """수록 주기 1종(PRD 응답 1행). 한 표가 여러 주기를 가질 수 있다(예: 분기+년)."""

    se_label: str                     # PRD_SE, 예 '년','월','분기'
    se_code: Optional[str]            # 요청 prdSe 코드 Y/M/Q/H/D (미지원 라벨이면 None)
    start: str                        # STRT_PRD_DE (원본 표기)
    end: str                          # END_PRD_DE (원본 표기)
    fmt: Optional[str]                # 요청 시점 형식 힌트(YYYY, YYYYMM…), 미지원이면 None


@dataclass
class TableMetadata:
    """ITM+PRD 를 통합 파싱한 통계표 메타데이터.

    items   : 항목 목록(ITM, OBJ_ID='ITEM')
    axes    : 분류축 목록(ITM, 그 외 OBJ_ID) — OBJ_ID_SN 오름차순
    periods : 수록 주기 목록(PRD) — 표가 분기+년 등 다중 주기를 줄 수 있어 리스트
    """

    org_id: str
    tbl_id: str
    tbl_nm: str
    items: list[Item] = field(default_factory=list)
    axes: list[Axis] = field(default_factory=list)
    periods: list[Period] = field(default_factory=list)

    @property
    def axis_count(self) -> int:
        return len(self.axes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "orgId": self.org_id,
            "tblId": self.tbl_id,
            "tblNm": self.tbl_nm,
            "items": [vars(i) for i in self.items],
            "axes": [vars(a) for a in self.axes],
            "periods": [vars(p) for p in self.periods],
        }


def _parse_items(itm_rows: list) -> list[Item]:
    return [
        Item(
            itm_id=str(r.get("ITM_ID", "")),
            itm_nm=str(r.get("ITM_NM", "")),
            unit=str(r.get("UNIT_NM", "")),
        )
        for r in itm_rows
        if isinstance(r, dict) and r.get("OBJ_ID") == "ITEM"
    ]


def _parse_axes(itm_rows: list) -> list[Axis]:
    groups: dict[str, list[dict]] = {}
    for r in itm_rows:
        if not isinstance(r, dict):
            continue
        oid = r.get("OBJ_ID")
        if oid and oid != "ITEM":
            groups.setdefault(oid, []).append(r)

    axes: list[Axis] = []
    for oid, rows in groups.items():
        try:
            sn = int(rows[0].get("OBJ_ID_SN"))
        except (TypeError, ValueError):
            sn = 0  # SN 없으면 0 → 아래 정렬에서 obj_id 알파벳으로 깨짐 방지
        axes.append(Axis(
            obj_id=str(oid),
            sn=sn,
            name=str(rows[0].get("OBJ_NM") or oid),
            values=[(str(r.get("ITM_ID", "")), str(r.get("ITM_NM", ""))) for r in rows],
        ))
    # OBJ_ID_SN 우선(알파벳 OBJ_ID 가 순차 아닐 수 있음 — 예 A,G), 동률은 obj_id.
    axes.sort(key=lambda a: (a.sn, a.obj_id))
    return axes


def _parse_periods(prd_rows: list) -> list[Period]:
    periods: list[Period] = []
    for r in prd_rows:
        if not isinstance(r, dict):
            continue
        label = str(r.get("PRD_SE", ""))
        code = _PRD_SE_CODE.get(label)
        periods.append(Period(
            se_label=label,
            se_code=code,
            start=str(r.get("STRT_PRD_DE", "")),
            end=str(r.get("END_PRD_DE", "")),
            fmt=_PRD_FMT.get(code) if code else None,
        ))
    return periods


def fetch_table_metadata(
    org_id: str,
    tbl_id: str,
    api_key: Optional[str] = None,
) -> TableMetadata:
    """통계표 1건의 ITM+PRD 를 병렬 조회·통합 파싱해 TableMetadata 로 반환한다.

    getMeta(ITM) → 항목(items)·분류축(axes, OBJ_ID_SN 순),
    getMeta(PRD) → 수록주기(periods, 다중 주기 가능)를 한 구조체로 합친다.
    어떤 표든(0~N축, 단일·다중 주기) 동일하게 처리한다.

    동기 함수다(map_claim_to_cell 이 sync 워커 스레드에서 호출). ITM·PRD 두 getMeta
    호출을 ThreadPoolExecutor 로 병렬 실행한다. rate limit·Session 은 공유 client 가 보장.

    Raises:
        KosisError: getMeta(ITM) 호출 실패 또는 ITM 응답이 list 가 아님(인증 실패 등).
        ValueError: API 키가 없는 경우.
    """
    key = resolve_api_key(api_key)  # 키 1회 검증/확보(스레드 진입 전)
    # 현재 컨텍스트(contextvars)를 워커 스레드로 복사 전파 — ThreadPoolExecutor 는
    # asyncio.to_thread 와 달리 자동 복사하지 않는다. 이게 없으면 스레드 안의 getMeta
    # 호출이 트레이싱 부모 span 을 잃고 orphan 트레이스가 된다.
    # 컨텍스트 복사본은 submit 마다 별도로 — 같은 Context 객체를 두 스레드가 동시에
    # ctx.run 하면 "already entered" 에러가 난다.
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_itm = ex.submit(contextvars.copy_context().run,
                          fetch_meta_item, org_id, tbl_id, "ITM", key)
        f_prd = ex.submit(contextvars.copy_context().run,
                          fetch_meta_item, org_id, tbl_id, "PRD", key)
        itm = f_itm.result()  # ITM 실패는 치명적 — 예외 그대로 전파
        # PRD 실패는 주기 없이 진행(periods=[]); KosisError 만 흡수, 그 외 예외는 전파.
        try:
            prd = f_prd.result()
        except KosisError as exc:
            logger.warning("KOSIS PRD 메타 실패 tbl=%s: %s", tbl_id, exc)
            prd = []

    if not isinstance(itm, list):
        raise KosisError(f"ITM 메타 형식 비정상(인증 실패?): {type(itm).__name__}")
    prd_rows = prd if isinstance(prd, list) else []

    # tbl_nm 은 ITM/PRD 응답에 없다 → 빈값. 표명이 필요하면 호출부가 search 결과로 채운다.
    meta = TableMetadata(
        org_id=org_id,
        tbl_id=tbl_id,
        tbl_nm="",
        items=_parse_items(itm),
        axes=_parse_axes(itm),
        periods=_parse_periods(prd_rows),
    )
    logger.info(
        "KOSIS 메타 tbl=%s: 항목 %d · 분류축 %d · 주기 %d",
        tbl_id, len(meta.items), meta.axis_count, len(meta.periods),
    )
    return meta
