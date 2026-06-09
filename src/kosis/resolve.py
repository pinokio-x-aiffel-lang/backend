"""KOSIS 셀 좌표 해소(retrieval funnel): claim + 선정표 → KosisQuery. [파이프라인 5 전반]

getMeta(type=ITM) 응답에서 항목(OBJ_ID='ITEM')과 분류축(OBJ_ID='A'/'B'…)을
가른 뒤, claim 의 subject/population 을 이름으로 매칭해 itmId·objL 코드를 정한다.
결정적 이름매칭만 사용(LLM 미사용); 매칭 실패는 ResolveError 로 알린다.

itmId/objL 코드의 출처가 ITM 메타라는 점은 metadata.py 참조. 분류축 값(OBJ_VAR)
전용 type 은 다수 표에서 빈 응답이라, 분류 코드도 ITM 응답 안의 OBJ_ID 로 구분한다.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional

from src.kosis.cell import KosisQuery
from src.kosis.metadata import fetch_meta_item
from src.kosis.synonyms import SYNONYMS as _SYNONYMS

logger = logging.getLogger("kosis")

# 분류축 값 매칭 폴백 콜백: (분류축 rows, population, 축이름) -> 선택한 ITM_ID | None.
# 규칙+동의어가 실패한 축에만 호출된다. 구현(예: LLM)은 상위 층(fetch_kosis_data)에
# 두고 주입한다 — resolve 자체는 외부 의존(LLM) 없이 결정적으로 유지.
AxisMatcher = Callable[[list[dict], str, str], Optional[str]]

# 분류축에서 '대상 미지정 시' 잡을 합계/전체 카테고리 이름 후보.
_TOTAL_NAMES = {"계", "전체", "합계", "전국", "소계", "총계"}
# 접미사 매칭용(예: '15세 이상 전체'). 짧고 모호한 '계'는 제외 — '통계/관계/시계'
# 같은 오탐 방지(그 짧은 토큰은 정확매칭 _TOTAL_NAMES 로만 잡는다).
_TOTAL_SUFFIXES = ("전체", "합계", "총계", "소계", "전국")

# 모집단 동의어(_SYNONYMS): claim '청년' → 축값 '15~29세' 갭을 메운다(case C).
# 도메인 데이터라 src/kosis/synonyms.py 로 분리. 표기차(15-29세/15~29세)는 _norm 흡수.

# 공백 + 하이픈/대시류(- ‐-―) + 물결(~)을 제거 — '15 - 29세'·'15~29세' 동일화.
_STRIP = re.compile(r"[\s\-‐-―~]")


class ResolveError(Exception):
    """셀 좌표 해소 실패(항목/분류 매칭 0건, 미지원 축 구성 등)."""


def _norm(s: Any) -> str:
    """공백·대시·물결 제거 정규화. 이름 비교용(연령대 표기차 흡수)."""
    return _STRIP.sub("", str(s or ""))


def _expand(target: str) -> list[str]:
    """target(정규화) + 동의어(정규화) 후보 목록. 빈 target 은 []."""
    t = _norm(target)
    if not t:
        return []
    out = [t]
    for alt in _SYNONYMS.get(t, []):
        n = _norm(alt)
        if n and n not in out:
            out.append(n)
    return out


def _match_code(rows: list[dict], target: str) -> Optional[str]:
    """rows 중 ITM_NM 이 target(또는 동의어)과 일치(정확>부분)하는 행의 ITM_ID.

    target 을 동의어로 확장(_expand)해 '청년'→'15~29세' 같은 갭을 메운다.
    부분 일치는 가장 짧은 이름을 골라(더 구체적) substring 함정을 줄인다. 없으면 None.
    """
    cands = _expand(target)
    if not cands:
        return None
    for c in cands:  # 정확 일치 우선(후보 순서 = 원어 > 동의어)
        for r in rows:
            if _norm(r.get("ITM_NM")) == c:
                return r.get("ITM_ID")
    partial = []  # 부분 일치(양방향)
    for r in rows:
        rn = _norm(r.get("ITM_NM"))
        if any(c and (c in rn or rn in c) for c in cands):
            partial.append(r)
    if partial:
        partial.sort(key=lambda r: len(_norm(r.get("ITM_NM"))))
        return partial[0].get("ITM_ID")
    return None


def _total_code(rows: list[dict]) -> Optional[str]:
    """분류축 rows 에서 합계/전체 카테고리 코드. 없으면 None.

    1) 정확매칭(_TOTAL_NAMES) 우선.
    2) 접미사 매칭(_TOTAL_SUFFIXES): '15세 이상 전체'처럼 총계가 장황하게 적힌 축을
       잡는다. 짧고 모호한 '계'는 1)에서만 처리(통계/관계 등 오탐 방지). 동률은 더
       짧은 이름(=총계스러움) 우선.
    """
    for r in rows:  # 1) 정확매칭
        if _norm(r.get("ITM_NM")) in _TOTAL_NAMES:
            return r.get("ITM_ID")
    suffixed = [r for r in rows if _norm(r.get("ITM_NM")).endswith(_TOTAL_SUFFIXES)]
    if suffixed:  # 2) 접미사 매칭(예: '15세이상전체' → 끝이 '전체')
        suffixed.sort(key=lambda r: len(_norm(r.get("ITM_NM"))))
        return suffixed[0].get("ITM_ID")
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
    axis_matcher: Optional[AxisMatcher] = None,
) -> tuple[Optional[KosisQuery], dict]:
    """resolve_cell_query 와 동일 로직이되 실패해도 raise 하지 않고 (query|None, trace) 반환.

    trace(dict): 표의 항목·분류축과 매칭 결과 — 디버깅/표시용.
      - items: [(ITM_ID, ITM_NM)]            표의 항목 목록
      - axes:  {분류축명: [(코드, 값명)]}     표의 분류축별 값 목록
      - itm_id, obj_codes                    매칭된 코드(성공 시)
      - error: str | None                    매칭 실패 사유(없으면 None)
      - match_source: "rule" | "llm"         population 을 무엇으로 매칭했나
    이름비교는 _norm(공백 제거) 기준이라 error 에도 공백 제거된 값을 싣는다.
    KosisError(getMeta 호출 실패)는 그대로 전파.

    axis_matcher: 규칙+동의어(_match_code)가 실패한 축에 대해 호출되는 선택적 폴백.
      (rows, population, axis_name) -> ITM_ID | None. 기본 None 이면 이 함수는
      LLM 등 외부 의존 없이 '결정적'으로 동작한다(설계 원칙). 반환 코드는 rows 의
      실제 ITM_ID 와 대조 검증해 환각을 차단한다. 호출 여부(=비용)는 상위(fetch_kosis_data)
      가 후보 전체를 보고 결정한다 — policy/mechanism 분리.
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
        # population 을 실제 축값에 매칭했는지. 어느 축에도 못 박고 합계로 대체하면
        # 그 셀은 '요청 집단'이 아니라 '전체'값 → population_fallback=True 로 표시.
        "population_matched": True, "population_fallback": False, "fallback_axes": [],
        "match_source": "rule",  # population 을 LLM 폴백으로 맞추면 "llm" 으로 바뀜
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

    pop_provided = bool(_norm(population))
    pop_match_count = 0          # population 을 '실제로' 매칭한 축 수(합계 폴백 제외)
    llm_used = False
    fallback_axes: list[str] = []
    codes: list[str] = []
    valid_codes = lambda rows: {str(r.get("ITM_ID")) for r in rows}  # noqa: E731
    for i, oid in enumerate(axis_ids):
        rows = axes[oid]
        matched = _match_code(rows, population)
        # 규칙+동의어 실패 시에만 LLM 폴백(있으면). 반환 코드는 rows 와 대조 검증.
        if matched is None and axis_matcher is not None and pop_provided:
            cand = axis_matcher(rows, population, str(rows[0].get("OBJ_NM") or oid))
            if cand is not None and str(cand) in valid_codes(rows):
                matched = str(cand)
                llm_used = True
        if matched is not None:
            code = matched
            pop_match_count += 1
        else:
            code = _total_code(rows)         # population 못 맞춘 축 → 합계로 대체
            if code is not None:
                if pop_provided:             # 요청 집단이 있었는데 합계로 떨어진 축 기록
                    fallback_axes.append(str(rows[0].get("OBJ_NM") or oid))
            elif i < 2:                      # 첫 두 축은 합계도 없으면 실패
                trace["error"] = f"분류축 {oid} 매칭 실패: population={_norm(population)!r}"
                return None, trace
            else:                            # 3번째+ 축은 "" (retry 가 "ALL" 확장)
                code = ""
        codes.append(code)
    trace["obj_codes"] = codes
    # 요청 집단(population)을 '어느 축에도' 못 박았으면 = 사실상 전체값 → 폴백 표시.
    trace["population_matched"] = pop_match_count > 0
    trace["population_fallback"] = pop_provided and pop_match_count == 0
    trace["fallback_axes"] = fallback_axes
    if llm_used:
        trace["match_source"] = "llm"

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
    axis_matcher: Optional[AxisMatcher] = None,
) -> KosisQuery:
    """선정표(org_id/tbl_id) + claim 좌표 → fetch_cell 입력 KosisQuery.

    - itmId: ITEM 행에서 subject 이름매칭 (실패 시 ResolveError).
    - objL1/objL2: 분류축(A,B…)에서 population 이름매칭, 없으면 합계 코드 폴백.
    - 분류축이 0개면 objL="" (분류 없는 표), 3개 이상은 미지원(ResolveError).
    - axis_matcher: 규칙+동의어 실패 축의 선택적 폴백(resolve_cell_query_traced 참조).

    Raises:
        KosisError: getMeta(ITM) 호출 실패/빈 응답.
        ResolveError: 항목/분류 매칭 실패 또는 분류축 >2개.
    """
    query, trace = resolve_cell_query_traced(
        org_id, tbl_id, subject=subject, population=population,
        period=period, period_se=period_se, api_key=api_key,
        axis_matcher=axis_matcher,
    )
    if query is None:
        raise ResolveError(trace["error"] or "셀 좌표 해소 실패")
    logger.info(
        "KOSIS 좌표 해소 tbl=%s itmId=%s objL=%s",
        tbl_id, query.itm_id, trace["obj_codes"] or "(없음)",
    )
    return query
