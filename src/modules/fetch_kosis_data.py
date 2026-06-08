from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone

from src.kosis import (
    KosisError,
    fetch_cell_with_retry,
    resolve_api_key,
    resolve_cell_query_traced,
)
from src.schemas.runtime import (
    CellAttempt,
    Claim,
    ClaimAnalysis,
    Evidence,
    KosisQuery,
    MasterSchema,
)

_DATA_API = "statisticsParameterData.do"


class FetchKosisDataError(Exception):
    """KOSIS 통계자료 조회 실패."""


async def fetch_kosis_data(master_schema: MasterSchema) -> None:
    """[5] KOSIS에서 검색해 온 상위 n개의 표에서 claim 좌표를 해소(resolve_cell_query)해 한 셀을 조회한다.

    analysis[*] 의 kosis_query(조회 로그)와 evidence(선정 셀, 실패 시 None)를 채운다.
    한 claim 실패(KosisError/ResolveError/ValueError)는 success=0 으로 기록하고 계속,
    그 외 예외만 raise → runner. claim 들은 to_thread + asyncio.gather 로 동시 조회
    (rate limit 은 공유 client 가 1000/min 이하로 강제).
    """
    api_key = resolve_api_key()  # 키 1회 확보(없으면 ValueError → runner 가 처리)
    claims = {c.claim_id: c for c in master_schema.claims}
    await asyncio.gather(
        *(
            _fetch_one(analysis, claims.get(analysis.claim_id), api_key)
            for analysis in master_schema.analysis
        )
    )


# 디버깅 표시용 항목/분류값 샘플 상한 (큰 표는 항목이 수백 개)
_ITEMS_CAP = 25
_AXIS_VALS_CAP = 15


async def _fetch_one(
    analysis: ClaimAnalysis, claim: Claim | None, api_key: str
) -> None:
    """analysis 1건 → 후보 표들을 RANK 순으로 조회, 첫 매칭 셀을 evidence 로 채운다.

    표별 시도 결과(항목·분류축·매칭 사유)를 cell_attempts 에 모아 '왜 못 찾았는지'
    디버깅을 돕는다. 매칭된 표 기준으로 kosis_query·evidence 를 제자리 변경한다.
    """
    t0 = time.perf_counter()
    if claim is None or not analysis.candidates:
        analysis.kosis_query = _log(
            "", success=0, error_msg="후보 표 또는 claim 없음", duration_ms=_ms(t0),
        )
        return

    period = _to_kosis_period(claim.period_type, claim.period_value.llm_value)
    matched, attempts = await asyncio.to_thread(
        _resolve_and_fetch_best, analysis.candidates, claim, period, api_key
    )
    analysis.cell_attempts = attempts  # 표별 조회 시도 기록(디버깅)

    if matched is None:
        reasons = [
            f"{a.tbl_id}: {a.error}"
            for a in attempts
            if a.error and not a.error.startswith("스킵")
        ]
        analysis.kosis_query = _log(
            "", success=0,
            error_msg=f"후보 {len(analysis.candidates)}개 모두 매칭 실패"
            + (f" (예: {reasons[0]})" if reasons else ""),
            duration_ms=_ms(t0),
        )
        return

    cand, query, cell = matched
    analysis.kosis_query = _log(
        cand.tbl_id, success=1, rows_returned=1,
        params=_params_log(query), duration_ms=_ms(t0),
    )
    analysis.evidence = _to_evidence(
        claim, cand.org_id, cand.tbl_id, query, cell, cand.tbl_nm,
    )


def _cap(names: list, n: int) -> list[str]:
    """이름 목록을 n개로 자르고, 넘치면 '…외 M개' 꼬리표를 단다(표시용)."""
    out = [str(x) for x in names[:n]]
    if len(names) > n:
        out.append(f"…외 {len(names) - n}개")
    return out


def _resolve_and_fetch_best(candidates, claim, period, api_key):
    """후보 표들을 RANK 순으로 좌표 해소(getMeta)+셀 조회. 첫 매칭에서 멈춘다.

    표마다 CellAttempt(항목·분류축·매칭 결과/사유)를 남긴다. 매칭 후 남은 후보는
    조회하지 않고 '스킵'으로만 기록한다(early-stop). to_thread 로 호출된다.

    Returns:
        (matched | None, attempts) — matched = (cand, query, cell).
    """
    attempts: list[CellAttempt] = []
    matched = None
    for cand in candidates:
        if matched is not None:  # early-stop: 더 조회하지 않음
            attempts.append(CellAttempt(
                tbl_id=cand.tbl_id, tbl_nm=cand.tbl_nm, error="스킵(앞에서 매칭됨)",
            ))
            continue
        try:
            query, trace = resolve_cell_query_traced(
                cand.org_id, cand.tbl_id,
                subject=claim.subject, population=claim.population,
                period=period, period_se=claim.period_type, api_key=api_key,
            )
        except (KosisError, ValueError) as exc:
            attempts.append(CellAttempt(
                tbl_id=cand.tbl_id, tbl_nm=cand.tbl_nm, error=f"메타 조회 실패: {exc}",
            ))
            continue

        att = CellAttempt(
            tbl_id=cand.tbl_id, tbl_nm=cand.tbl_nm,
            itm_id=trace.get("itm_id"),
            items=_cap([nm for _id, nm in trace["items"]], _ITEMS_CAP),
            axes={
                ax: _cap([nm for _id, nm in vals], _AXIS_VALS_CAP)
                for ax, vals in trace["axes"].items()
            },
        )
        if query is None:  # 좌표 해소 실패(항목/분류 매칭 실패)
            att.error = trace.get("error")
            attempts.append(att)
            continue
        try:
            cell = fetch_cell_with_retry(query, api_key)
        except (KosisError, ValueError) as exc:
            att.error = f"셀 조회 실패: {exc}"
            attempts.append(att)
            continue
        if cell is None:
            att.error = "셀 매칭 0건(시점/분류 불일치)"
            attempts.append(att)
            continue
        att.matched = True
        att.value = cell.value
        att.unit = cell.unit
        attempts.append(att)
        matched = (cand, query, cell)
    return matched, attempts


def _to_kosis_period(period_type: str, raw: str) -> str:
    """claim 시점값 → KOSIS PRD_DE 형식.

    Y: "2024"    → "2024"   (4자리)
    M: "2024-01" → "202401" (YYYYMM, 6자리)
    Q: "2024-Q1" → "202401" (YYYYQQ, 01~04, 6자리)
    S: "2024-H1" → "202401" (YYYYHH, 01~02, 6자리)
    """
    s = str(raw or "")
    if period_type == "Y":
        return re.sub(r"\D", "", s)[:4]
    if period_type == "Q":
        m = re.match(r"(\d{4})-Q([1-4])", s)
        if m:
            return f"{m.group(1)}{int(m.group(2)):02d}"
    if period_type == "S":
        m = re.match(r"(\d{4})-H([12])", s)
        if m:
            return f"{m.group(1)}{int(m.group(2)):02d}"
    return re.sub(r"\D", "", s)


def _log(tbl_id, *, success, rows_returned=0, params="", error_msg=None, duration_ms=0):
    return KosisQuery(
        api=_DATA_API, tbl_id=tbl_id, params=params,
        rows_returned=rows_returned, success=success,
        error_msg=error_msg, duration_ms=duration_ms,
    )


def _params_log(query) -> str:
    """조회 파라미터를 로그용 JSON 으로. apiKey 는 절대 포함하지 않는다."""
    return json.dumps(
        {
            "method": "getList", "orgId": query.org_id, "tblId": query.tbl_id,
            "itmId": query.itm_id,
            "objL1": query.obj_l1, "objL2": query.obj_l2,
            "objL3": query.obj_l3, "objL4": query.obj_l4,
            "prdSe": query.period_se, "startPrdDe": query.period,
            "endPrdDe": query.period, "match_filters": query.match_filters,
        },
        ensure_ascii=False,
    )


def _to_evidence(claim, org_id, tbl_id, query, cell, table_name) -> Evidence:
    """KosisCell → Evidence. unit/period 는 KOSIS 응답값을 그대로 싣는다."""
    return Evidence(
        claim_id=claim.claim_id, source="KOSIS",
        subject=claim.subject, unit=cell.unit,
        period_type=claim.period_type, period=cell.period,
        population=claim.population, value=cell.value,
        kosis_org_id=org_id, kosis_tbl_id=tbl_id, table_name=table_name,
        kosis_item_id=query.itm_id, classification=dict(query.match_filters),
        last_updated=cell.lst_chn_de,
        retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
