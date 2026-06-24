from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import replace
from datetime import datetime, timezone

from src.kosis import (
    KosisError,
    fetch_cell_with_retry,
    map_claim_to_cell_query_traced,
    resolve_api_key,
)
from src.llm.client import LlmError
from src.observability.tracing import traced_chat
from src.llm.model_presets import RESOLVE_AXIS_MATCH, RESOLVE_ITEM_MATCH
from src.prompts.prompts import (
    RESOLVE_AXIS_MATCH_SYSTEM,
    RESOLVE_AXIS_MATCH_USER,
    RESOLVE_ITEM_MATCH_SYSTEM,
    RESOLVE_ITEM_MATCH_USER,
)
from src.schemas.runtime import (
    CellAttempt,
    Claim,
    ClaimAnalysis,
    ClaimType,
    Evidence,
    KosisQuery,
    MasterSchema,
)

_DATA_API = "statisticsParameterData.do"

logger = logging.getLogger("kosis")

# LLM 분류축 매칭 응답 구조(structured outputs). 보기 코드 중 하나 또는 기권(null).
# obj_code 도 required — 안 그러면 모델이 {"matched":true}만 주고 코드를 누락한다(실측).
_AXIS_MATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "obj_code": {"type": ["string", "null"]},
        "matched": {"type": "boolean"},
    },
    "required": ["matched", "obj_code"],
}
# LLM 에 보여줄 분류축 값 보기 상한(축이 수백 값이면 토큰 폭증 방지).
_AXIS_OPTIONS_CAP = 60

# LLM 항목 매칭 응답 구조(structured outputs). 항목 코드 중 하나 또는 기권(null).
_ITEM_MATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "itm_code": {"type": ["string", "null"]},
        "matched": {"type": "boolean"},
    },
    "required": ["matched", "itm_code"],
}


class FetchKosisDataError(Exception):
    """KOSIS 통계자료 조회 실패."""


async def fetch_kosis_data(master_schema: MasterSchema) -> None:
    """[5] KOSIS에서 검색해 온 상위 n개의 표에서 claim 좌표를 매핑(map_claim_to_cell_query)해 한 셀을 조회한다.

    analysis[*] 의 kosis_query(조회 로그)와 evidence(선정 셀, 실패 시 None)를 채운다.
    한 claim 실패(KosisError/ClaimMappingError/ValueError)는 success=0 으로 기록하고 계속,
    그 외 예외만 raise → runner. claim 간(asyncio.gather)·한 claim 의 후보 표 간
    (to_thread + gather) 모두 동시 조회한다(rate limit 은 공유 client 가 1000/min 이하로 강제).
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
_PASS2_LLM_CAP = 5  # claim당 Pass2 LLM 재조회 상한(비용 게이팅)


def _select_match(results: list[tuple]) -> tuple | None:
    """매칭된 표 중 선정: 모집단을 '실제로' 맞춘 표(비폴백) 우선, 없으면 합계 폴백 표.
    각 그룹 내에선 RANK(인덱스 작은) 순 — results 가 후보 RANK 순이라 그대로 first."""
    pairs = [(att, m) for att, m in results if m is not None]
    return next(
        (p for p in pairs if not p[0].population_fallback),
        pairs[0] if pairs else None,
    )


async def _fetch_one(
    analysis: ClaimAnalysis, claim: Claim | None, api_key: str
) -> None:
    """analysis 1건 → 후보 표들을 동시 조회, 매칭된 표 중 RANK 우선으로 evidence 를 채운다.

    표별 시도 결과(항목·분류축·매칭 사유)를 cell_attempts 에 모아 '왜 못 찾았는지'
    디버깅을 돕는다. 매칭된 표 기준으로 kosis_query·evidence 를 제자리 변경한다.

    2-pass: [1] 결정적(규칙+동의어)으로 후보 전체 동시 조회 → 모집단 특정값 얻으면 끝.
    [2] 못 얻었고(폴백/실패) population 이 있으면 RANK 순 LLM 폴백 재조회(첫 성공에서 중단).
    LLM 호출 여부는 후보 전체를 본 이 상위 함수가 결정한다(비용 게이팅)."""
    t0 = time.perf_counter()
    if claim is None or not analysis.candidates:
        analysis.kosis_query = _log(
            "", success=0, error_msg="후보 표 또는 claim 없음", duration_ms=_ms(t0),
        )
        return

    period = _to_kosis_period(claim.period_type, claim.period_value.llm_value)
    # [Pass 1] 후보 표 전체 동시 조회(결정적, LLM 미사용). early-stop 없이 모두 시도.
    results = list(await asyncio.gather(
        *(
            asyncio.to_thread(_resolve_and_fetch_one, cand, claim, period, api_key)
            for cand in analysis.candidates
        )
    ))
    chosen = _select_match(results)

    # [Pass 2] 결정적으로 못 얻었으면 LLM 폴백 재조회 — 두 갈래를 한 번에 메운다:
    #   (1) 항목(itm) 미매칭 표: _llm_item_matcher 로 subject→itmId (예: 상승률→전년동월비)
    #   (2) 모집단 폴백 표: _llm_axis_matcher 로 population→분류축 코드
    # 트리거: 아직 모집단 특정값을 못 얻었고(폴백/실패), 모집단이 있거나 항목 미매칭 표가
    # 있을 때. RANK 순 순차, 특정 매칭 첫 성공에서 중단 → claim 당 LLM 호출 최소화.
    # 항목 미매칭 표가 있으면, 이미 다른 표가 (지수레벨 등으로) 매칭됐더라도 LLM 패스를
    # 돈다 — 그 미매칭 표(예: 등락률)가 사실 정답일 수 있어 evidence 에 넣어야 [6]이 고른다.
    has_unmatched_itm = any(att.itm_id is None for att, _ in results)
    need_llm = chosen is None or chosen[0].population_fallback or has_unmatched_itm
    if need_llm:
        llm_tries = 0
        for i, cand in enumerate(analysis.candidates):
            if llm_tries >= _PASS2_LLM_CAP:
                break
            base = results[i][0]
            if results[i][1] is not None and not base.population_fallback:
                continue                            # 이미 모집단까지 특정 매칭(스킵)
            llm_tries += 1
            att2, m2 = await asyncio.to_thread(
                _resolve_and_fetch_one, cand, claim, period, api_key,
                _llm_axis_matcher, _llm_item_matcher,
            )
            results[i] = (att2, m2)                 # 기록 갱신(LLM 결과 반영)
            if m2 is not None and not att2.population_fallback:
                logger.info(
                    "KOSIS LLM 매칭 성공: claim=%s tbl=%s itm=%s",
                    claim.claim_id, cand.tbl_id, att2.itm_id,
                )
                break                               # 특정값 확보 → 중단
        chosen = _select_match(results)

    attempts = [att for att, _ in results]  # 후보 순서(=RANK 순) 유지
    analysis.cell_attempts = attempts  # 표별 조회 시도 기록(디버깅)

    # [5b] change_rate 두 시점 계산: 품목별처럼 '전년동월비' 항목이 없어 지수 레벨만
    # 잡힌 표(itm_is_rate=False)는, 동일 좌표의 전년 동기 셀을 한 번 더 조회해
    # (now/prev−1)×100 (%) 로 변화율을 직접 계산한다. 등락률 항목(itm_is_rate=True)은
    # 셀값이 이미 변화율이라 그대로 둔다. 실패(전년 셀 없음 등)는 override 없음 → 원래 값.
    rate_override = await _change_rate_overrides(claim, results, period, api_key)

    # [5] 고르지 않고, 매칭된 모든 후보 셀을 evidences 로 내보낸다(RANK 순) — [7]이 n:1 비교.
    analysis.evidences = [
        _to_evidence(
            claim, m[0].org_id, m[0].tbl_id, m[1], m[2], m[0].tbl_nm,
            population_fallback=att.population_fallback, match_source=att.match_source,
            value_override=rate_override.get(idx),
        )
        for idx, (att, m) in enumerate(results) if m is not None  # m = (cand, query, cell)
    ]

    if chosen is None:
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

    # 매칭된 모든 셀은 위에서 analysis.evidences 에 담았다. 여기선 로그/경고만.
    # (표 선정은 [6] rank_evidence, 비교는 [7] 가 evidences[0]부터 수행)
    chosen_att, (cand, query, _cell) = chosen
    if chosen_att.population_fallback:
        logger.warning(
            "KOSIS 모집단 폴백: claim=%s population=%r 미매칭 → 전체값으로 대체 (tbl=%s)",
            claim.claim_id, claim.population, cand.tbl_id,
        )
    analysis.kosis_query = _log(
        cand.tbl_id, success=1, rows_returned=len(analysis.evidences),
        params=_params_log(query), duration_ms=_ms(t0),
    )


def _cap(names: list, n: int) -> list[str]:
    """이름 목록을 n개로 자르고, 넘치면 '…외 M개' 꼬리표를 단다(표시용)."""
    out = [str(x) for x in names[:n]]
    if len(names) > n:
        out.append(f"…외 {len(names) - n}개")
    return out


def _llm_axis_matcher(
    values: list[tuple[str, str]], population: str, axis_name: str
) -> str | None:
    """규칙+동의어 실패 축의 LLM 폴백: 보기(코드:이름) 중 population 에 맞는 코드.

    map_claim_to_cell 에 주입되는 AxisMatcher. 닫힌 보기 중 선택(+기권)이라 환각 위험이
    낮고, 반환 코드의 대조 검증은 map_claim_to_cell 이 한 번 더 한다. 호출 실패/기권은 None.
    HCX-007 structured outputs 로 형식을 강제한다. (LlmCaller 경유 = traced_chat)
    """
    options = "\n".join(
        f"  {code}: {name}" for code, name in values[:_AXIS_OPTIONS_CAP]
    )
    messages = [
        {"role": "system", "content": RESOLVE_AXIS_MATCH_SYSTEM},
        {"role": "user", "content": RESOLVE_AXIS_MATCH_USER.format(
            target=population, axis_name=axis_name, options=options,
        )},
    ]
    try:
        resp = traced_chat(
            model_alias=RESOLVE_AXIS_MATCH.model_alias,
            model_name=RESOLVE_AXIS_MATCH.model_name,
            messages=messages,
            max_tokens=RESOLVE_AXIS_MATCH.max_tokens,
            temperature=RESOLVE_AXIS_MATCH.temperature,
            json_structure=_AXIS_MATCH_SCHEMA,
            trace_name="fetch_kosis_data:axis_match",
        )
    except (LlmError, AttributeError) as exc:
        logger.warning("KOSIS 분류축 LLM 매칭 실패(%s): %s", axis_name, exc)
        return None
    try:
        data = json.loads(resp.text.strip())
    except (json.JSONDecodeError, AttributeError):
        return None
    if not data.get("matched"):
        return None
    code = data.get("obj_code")
    return str(code) if code is not None else None


def _llm_item_matcher(values: list[tuple[str, str]], subject: str) -> str | None:
    """규칙 이름매칭 실패 항목의 LLM 폴백: 보기(코드:이름) 중 subject 에 맞는 항목 코드.

    map_claim_to_cell 에 주입되는 ItemMatcher. 닫힌 보기 중 선택(+기권)이라 환각 위험이
    낮고, 반환 코드의 대조 검증은 map_claim_to_cell 이 한 번 더 한다. 호출 실패/기권은 None.
    주 용도: '소비자물가 상승률'처럼 항목명 직매칭이 안 되는 주제 → '전년동월비(%)'.
    """
    options = "\n".join(
        f"  {code}: {name}" for code, name in values[:_AXIS_OPTIONS_CAP]
    )
    messages = [
        {"role": "system", "content": RESOLVE_ITEM_MATCH_SYSTEM},
        {"role": "user", "content": RESOLVE_ITEM_MATCH_USER.format(
            subject=subject, options=options,
        )},
    ]
    try:
        resp = traced_chat(
            model_alias=RESOLVE_ITEM_MATCH.model_alias,
            model_name=RESOLVE_ITEM_MATCH.model_name,
            messages=messages,
            max_tokens=RESOLVE_ITEM_MATCH.max_tokens,
            temperature=RESOLVE_ITEM_MATCH.temperature,
            json_structure=_ITEM_MATCH_SCHEMA,
            trace_name="fetch_kosis_data:item_match",
        )
    except (LlmError, AttributeError) as exc:
        logger.warning("KOSIS 항목 LLM 매칭 실패: %s", exc)
        return None
    try:
        data = json.loads(resp.text.strip())
    except (json.JSONDecodeError, AttributeError):
        return None
    if not data.get("matched"):
        return None
    code = data.get("itm_code")
    return str(code) if code is not None else None


def _resolve_and_fetch_one(cand, claim, period, api_key, axis_matcher=None,
                           item_matcher=None):
    """후보 표 1건을 좌표 해소(getMeta)+셀 조회. to_thread 로 동시 호출된다.

    axis_matcher: 규칙+동의어 실패 축의 폴백(보통 None=결정적; Pass2 에서만 LLM 주입).

    Returns:
        (CellAttempt, matched | None) — matched = (cand, query, cell).
        매칭 실패 사유는 CellAttempt.error 에, 항목·분류축은 디버깅용으로 남긴다.
    """
    try:
        query, trace = map_claim_to_cell_query_traced(
            cand.org_id, cand.tbl_id,
            subject=claim.subject, population=claim.population,
            period=period, period_se=claim.period_type, api_key=api_key,
            axis_matcher=axis_matcher, item_matcher=item_matcher,
        )
    except (KosisError, ValueError) as exc:
        return CellAttempt(
            tbl_id=cand.tbl_id, tbl_nm=cand.tbl_nm, error=f"메타 조회 실패: {exc}",
        ), None

    att = CellAttempt(
        tbl_id=cand.tbl_id, tbl_nm=cand.tbl_nm,
        itm_id=trace.get("itm_id"),
        items=_cap([nm for _id, nm in trace["items"]], _ITEMS_CAP),
        axes={
            ax: _cap([nm for _id, nm in vals], _AXIS_VALS_CAP)
            for ax, vals in trace["axes"].items()
        },
        population_fallback=bool(trace.get("population_fallback")),
        match_source=str(trace.get("match_source") or "rule"),
        itm_is_rate=bool(trace.get("itm_is_rate")),
    )
    if query is None:  # 좌표 해소 실패(항목/분류 매칭 실패)
        att.error = trace.get("error")
        return att, None
    try:
        cell = fetch_cell_with_retry(query, api_key)
    except (KosisError, ValueError) as exc:
        att.error = f"셀 조회 실패: {exc}"
        return att, None
    if cell is None:
        att.error = "셀 매칭 0건(시점/분류 불일치)"
        return att, None
    att.matched = True
    att.value = cell.value
    att.unit = cell.unit
    return att, (cand, query, cell)


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


async def _change_rate_overrides(
    claim: Claim, results: list, period: str, api_key: str
) -> dict[int, float]:
    """change_rate claim 의 '지수 레벨' 매칭 표를 전년 동기 셀로 YoY 직접계산한 값 맵.

    반환: {results index → 변화율(%)}. 등락률 항목(itm_is_rate)·계산 실패는 제외.
    """
    if claim.claim_type != ClaimType.CHANGE_RATE:
        return {}
    prev_period = _yoy_prev_period(period, claim.period_type)
    if not prev_period:
        return {}
    out: dict[int, float] = {}
    for idx, (att, m) in enumerate(results):
        if m is None or att.itm_is_rate:
            continue                       # 비율 항목이면 셀값이 이미 변화율
        _cand, query, cell = m
        rate = await asyncio.to_thread(_compute_yoy, query, cell, prev_period, api_key)
        if rate is not None:
            out[idx] = rate
            logger.info(
                "KOSIS YoY 직접계산: claim=%s tbl=%s %s→%s rate=%.2f%%",
                claim.claim_id, query.tbl_id, prev_period, period, rate,
            )
    return out


def _yoy_prev_period(period: str, period_type: str) -> str | None:
    """전년 동기 KOSIS 기간 — 연도 4자리만 −1 (M/Q/S 는 뒤 2자리 유지). 파싱불가 None."""
    p = str(period or "")
    return str(int(p[:4]) - 1) + p[4:] if len(p) >= 4 and p[:4].isdigit() else None


def _compute_yoy(query: KosisQuery, cell, prev_period: str, api_key: str) -> float | None:
    """동일 좌표의 전년 동기 셀을 조회해 (now/prev−1)×100(%) 반환. 실패 시 None."""
    try:
        now = float(cell.value)
        prev_cell = fetch_cell_with_retry(replace(query, period=prev_period), api_key)
        if prev_cell is None or prev_cell.value is None:
            return None
        prev = float(prev_cell.value)
        if prev == 0:
            return None
        return round((now / prev - 1) * 100, 4)
    except (KosisError, ValueError, TypeError):
        return None


def _to_evidence(
    claim, org_id, tbl_id, query, cell, table_name,
    population_fallback=False, match_source="rule", value_override=None,
) -> Evidence:
    """KosisCell → Evidence. unit/period 는 KOSIS 응답값을 그대로 싣는다.

    population_fallback=True 면 요청 모집단을 못 맞춰 전체값으로 대체됐다는 표시.
    match_source 는 모집단 매칭 출처("rule"|"llm").
    value_override 가 있으면(change_rate 두시점 계산) 셀값 대신 그 변화율(%)을 싣는다.
    """
    return Evidence(
        claim_id=claim.claim_id, source="KOSIS",
        subject=claim.subject,
        unit="%" if value_override is not None else cell.unit,
        period_type=claim.period_type, period=cell.period,
        population=claim.population,
        value=value_override if value_override is not None else cell.value,
        kosis_org_id=org_id, kosis_tbl_id=tbl_id, table_name=table_name,
        kosis_item_id=query.itm_id, classification=dict(query.match_filters),
        last_updated=cell.lst_chn_de,
        retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        population_fallback=population_fallback,
        match_source=match_source,
    )


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
