"""KOSIS 셀 좌표 해소(retrieval funnel): claim + 선정표 → KosisQuery. [파이프라인 5 전반]

getMeta(type=ITM) 응답에서 항목(OBJ_ID='ITEM')과 분류축(OBJ_ID='A'/'B'…)을
가른 뒤, claim 의 subject/population 을 이름으로 매칭해 itmId·objL 코드를 정한다.
결정적 이름매칭만 사용(LLM 미사용); 매칭 실패는 ResolveError 로 알린다.

itmId/objL 코드의 출처가 ITM 메타라는 점은 metadata.py 참조. 분류축 값(OBJ_VAR)
전용 type 은 다수 표에서 빈 응답이라, 분류 코드도 ITM 응답 안의 OBJ_ID 로 구분한다.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.kosis.cell import KosisQuery
from src.kosis.metadata import fetch_meta_item

logger = logging.getLogger("kosis")

# 분류축에서 '대상 미지정 시' 잡을 합계/전체 카테고리 이름 후보.
_TOTAL_NAMES = {"계", "전체", "합계", "전국", "소계", "총계"}


class ResolveError(Exception):
    """셀 좌표 해소 실패(항목/분류 매칭 0건, 미지원 축 구성 등)."""


def _norm(s: Any) -> str:
    """공백 제거 정규화. 이름 비교용."""
    return "".join(str(s or "").split())


def _match_code(rows: list[dict], target: str) -> Optional[str]:
    """rows 중 ITM_NM 이 target 과 일치(정확>부분)하는 행의 ITM_ID. 없으면 None.

    부분 일치는 가장 짧은 이름을 골라(더 구체적) substring 함정을 줄인다.
    """
    t = _norm(target)
    if not t:
        return None
    for r in rows:  # 정확 일치 우선
        if _norm(r.get("ITM_NM")) == t:
            return r.get("ITM_ID")
    cands = [
        r for r in rows
        if t in _norm(r.get("ITM_NM")) or _norm(r.get("ITM_NM")) in t
    ]
    if cands:
        cands.sort(key=lambda r: len(_norm(r.get("ITM_NM"))))
        return cands[0].get("ITM_ID")
    return None


def _total_code(rows: list[dict]) -> Optional[str]:
    """분류축 rows 에서 합계/전체 카테고리 코드. 없으면 None."""
    for r in rows:
        if _norm(r.get("ITM_NM")) in _TOTAL_NAMES:
            return r.get("ITM_ID")
    return None


def resolve_cell_query_traced(
    org_id: str,
    tbl_id: str,
    *,
    subject: str,
    population: str,
    period: str,
    period_se: str,
    api_key: Optional[str] = None,
) -> tuple[Optional[KosisQuery], dict]:
    """resolve_cell_query 와 동일 로직이되 실패해도 raise 하지 않고 (query|None, trace) 반환.

    trace(dict): 표의 항목·분류축과 매칭 결과 — 디버깅/표시용.
      - items: [(ITM_ID, ITM_NM)]            표의 항목 목록
      - axes:  {분류축명: [(코드, 값명)]}     표의 분류축별 값 목록
      - itm_id, obj_codes                    매칭된 코드(성공 시)
      - error: str | None                    매칭 실패 사유(없으면 None)
    이름비교는 _norm(공백 제거) 기준이라 error 에도 공백 제거된 값을 싣는다.
    KosisError(getMeta 호출 실패)는 그대로 전파.
    """
    itm = fetch_meta_item(org_id, tbl_id, "ITM", api_key)
    if not isinstance(itm, list):
        return None, {
            "items": [], "axes": {}, "itm_id": None, "obj_codes": [],
            "error": f"ITM 메타 형식 비정상: {type(itm).__name__}",
        }

    items = [r for r in itm if isinstance(r, dict) and r.get("OBJ_ID") == "ITEM"]
    axes: dict[str, list[dict]] = {}
    for r in itm:
        if not isinstance(r, dict):
            continue
        oid = r.get("OBJ_ID")
        if oid and oid != "ITEM":
            axes.setdefault(oid, []).append(r)

    trace: dict = {
        "items": [(r.get("ITM_ID"), r.get("ITM_NM")) for r in items],
        "axes": {
            (rows[0].get("OBJ_NM") or oid): [
                (r.get("ITM_ID"), r.get("ITM_NM")) for r in rows
            ]
            for oid, rows in axes.items()
        },
        "itm_id": None, "obj_codes": [], "error": None,
    }

    itm_id = _match_code(items, subject)
    if itm_id is None:
        trace["error"] = f"itmId 매칭 실패: subject={_norm(subject)!r}"
        return None, trace
    trace["itm_id"] = itm_id

    axis_ids = sorted(axes)  # 'A','B',… → objL1, objL2 순서
    if len(axis_ids) > 4:
        trace["error"] = f"분류축 {len(axis_ids)}개(>4) 미지원: {axis_ids}"
        return None, trace

    codes: list[str] = []
    for i, oid in enumerate(axis_ids):
        rows = axes[oid]
        code = _match_code(rows, population) or _total_code(rows)
        if code is None:
            if i < 2:  # 첫 두 축은 매칭 필수 — 반환 실패
                trace["error"] = f"분류축 {oid} 매칭 실패: population={_norm(population)!r}"
                return None, trace
            else:  # 3번째 이상 축은 "" 폴백 (fetch_cell_with_retry 가 "ALL" 확장 처리)
                code = ""
        codes.append(code)
    trace["obj_codes"] = codes

    # match_filters: "" 또는 "ALL" 인 축은 제외 (특정 코드가 없는 축은 필터링 불필요)
    filter_codes = [(i, c) for i, c in enumerate(codes) if c and c != "ALL"]

    query = KosisQuery(
        org_id=org_id,
        tbl_id=tbl_id,
        itm_id=itm_id,
        period=period,
        period_se=period_se,
        # 코드를 직접 박는 B 방식. 분류 없는 축은 "" (ALL 기본값 덮어씀).
        obj_l1=codes[0] if len(codes) >= 1 else "",
        obj_l2=codes[1] if len(codes) >= 2 else "",
        obj_l3=codes[2] if len(codes) >= 3 else "",
        obj_l4=codes[3] if len(codes) >= 4 else "",
        # 서버가 여러 행을 줘도 한 셀로 좁히도록 코드 매칭도 건다.
        match_filters={f"C{i + 1}": c for i, c in filter_codes},
    )
    return query, trace


def resolve_cell_query(
    org_id: str,
    tbl_id: str,
    *,
    subject: str,
    population: str,
    period: str,
    period_se: str,
    api_key: Optional[str] = None,
) -> KosisQuery:
    """선정표(org_id/tbl_id) + claim 좌표 → fetch_cell 입력 KosisQuery.

    - itmId: ITEM 행에서 subject 이름매칭 (실패 시 ResolveError).
    - objL1/objL2: 분류축(A,B…)에서 population 이름매칭, 없으면 합계 코드 폴백.
    - 분류축이 0개면 objL="" (분류 없는 표), 3개 이상은 미지원(ResolveError).

    Raises:
        KosisError: getMeta(ITM) 호출 실패/빈 응답.
        ResolveError: 항목/분류 매칭 실패 또는 분류축 >2개.
    """
    query, trace = resolve_cell_query_traced(
        org_id, tbl_id, subject=subject, population=population,
        period=period, period_se=period_se, api_key=api_key,
    )
    if query is None:
        raise ResolveError(trace["error"] or "셀 좌표 해소 실패")
    logger.info(
        "KOSIS 좌표 해소 tbl=%s itmId=%s objL=%s",
        tbl_id, query.itm_id, trace["obj_codes"] or "(없음)",
    )
    return query
