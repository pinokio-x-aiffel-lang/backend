from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import re
import time
from datetime import datetime, timezone

from src.kosis import (
    KosisError,
    fetch_cell_with_retry,
    map_claim_to_cell_query_traced,
    resolve_api_key,
)
from src.kosis.client import kosis_call_count
from src.llm.client import LlmError
from src.observability.tracing import traced_chat
from src.llm.model_presets import RESOLVE_AXIS_MATCH
from src.prompts.prompts import (
    RESOLVE_AXIS_MATCH_SYSTEM,
    RESOLVE_AXIS_MATCH_USER,
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

# Pass2 에서 claim 당 LLM 재조회할 후보 표 상한 (비용 게이팅).
_PASS2_LLM_CAP = 5


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
    _kc = [0]
    kosis_call_count.set(_kc)  # 이 claim 의 [5] KOSIS 호출 카운트(to_thread 로 공유)
    if claim is None or not analysis.candidates:
        analysis.kosis_query = _log(
            "", success=0, error_msg="후보 표 또는 claim 없음", duration_ms=_ms(t0),
        )
        analysis.kosis_calls += _kc[0]
        return

    period = _to_kosis_period(claim.period_type, claim.period_value.llm_value)
    # CHANGE_RATE(증감)면 기준 시점도 같은 셀 좌표로 조회해 evidence.compare_value 에 담는다.
    compare_period = _compare_period(claim)
    # [Pass 1] 후보 표 전체 동시 조회(결정적, LLM 미사용). early-stop 없이 모두 시도.
    results = list(await asyncio.gather(
        *(
            asyncio.to_thread(
                _resolve_and_fetch_one, cand, claim, period, api_key,
                None, None, compare_period,
            )
            for cand in analysis.candidates
        )
    ))
    chosen = _select_match(results)

    # [Pass 2] LLM 폴백 재조회 — 항목(itmId) 미매칭이나 모집단 폴백/미매칭 후보를 RANK 순.
    # 항목 실패는 population 유무와 무관 → 확보 실패(chosen None)면 항상 시도. 분류축·항목
    # 둘 다 LLM 폴백 주입. claim 당 재조회는 _PASS2_LLM_CAP 개로 제한(비용 게이팅), 첫 성공 중단.
    pop = (claim.population or "").strip()
    if chosen is None or chosen[0].population_fallback:
        llm_tries = 0
        for i, cand in enumerate(analysis.candidates):
            if llm_tries >= _PASS2_LLM_CAP:
                break
            att_i, m_i = results[i]
            if m_i is not None and not att_i.population_fallback:
                continue                            # 이미 모집단 특정값(스킵)
            # 재조회가 의미 있는 경우만: 항목 미매칭(항목 LLM) 또는 모집단 폴백/미매칭(축 LLM).
            retryable = att_i.itm_id is None or (pop and (att_i.population_fallback or m_i is None))
            if not retryable:
                continue
            llm_tries += 1
            att2, m2 = await asyncio.to_thread(
                _resolve_and_fetch_one, cand, claim, period, api_key,
                _llm_axis_matcher, _llm_axis_matcher, compare_period,  # 분류축+항목 LLM, 증감 기준시점
            )
            results[i] = (att2, m2)                  # 기록 갱신(LLM 결과 반영)
            if m2 is not None and not att2.population_fallback:
                logger.info(
                    "KOSIS LLM 매칭 성공(Pass2): claim=%s tbl=%s",
                    claim.claim_id, cand.tbl_id,
                )
                break                                # 특정값 확보 → 중단
        chosen = _select_match(results)

    attempts = [att for att, _ in results]  # 후보 순서(=RANK 순) 유지
    analysis.cell_attempts = attempts  # 표별 조회 시도 기록(디버깅)

    # [5] 고르지 않고, 매칭된 모든 후보 셀을 evidences 로 내보낸다(RANK 순) — [7]이 n:1 비교.
    analysis.evidences = [
        _to_evidence(
            claim, m[0].org_id, m[0].tbl_id, m[1], m[2], m[0].tbl_nm,
            population_fallback=att.population_fallback, match_source=att.match_source,
            compare_cell=m[3],
        )
        for att, m in results if m is not None  # m = (cand, query, cell, compare_cell)
    ]

    # [Pass 3] 값앵커 역매칭(절대형): 비폴백 확정 매치가 없으면 후보 슬라이스에서 값+라벨
    # 셀을 직접 찾아 evidence 앞에 추가(라벨검증=비폴백 → [7] _decide_metric 값앵커가 T 승격).
    if claim.claim_type in _REVERSE_TYPES and not _has_value_match(claim, analysis.evidences):
        rev = _reverse_match_candidates(claim, analysis.candidates, period, api_key)
        if rev:
            analysis.evidences = rev + analysis.evidences

    if chosen is None and not analysis.evidences:
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
        analysis.kosis_calls += _kc[0]
        return

    # 매칭된 모든 셀은 위에서 analysis.evidences 에 담았다. 여기선 로그/경고만.
    # (표 선정은 [6] rank_evidence, 비교는 [7] 가 evidences[0]부터 수행)
    if chosen is not None:
        chosen_att, (cand, query, _cell, _compare_cell) = chosen
        if chosen_att.population_fallback:
            logger.warning(
                "KOSIS 모집단 폴백: claim=%s population=%r 미매칭 → 전체값으로 대체 (tbl=%s)",
                claim.claim_id, claim.population, cand.tbl_id,
            )
        analysis.kosis_query = _log(
            cand.tbl_id, success=1, rows_returned=len(analysis.evidences),
            params=_params_log(query), duration_ms=_ms(t0),
        )
    else:
        # 결정적 매치는 없고 Pass3 역매칭만 성공한 경우.
        analysis.kosis_query = _log(
            analysis.evidences[0].kosis_tbl_id, success=1,
            rows_returned=len(analysis.evidences), duration_ms=_ms(t0),
        )
    analysis.kosis_calls += _kc[0]


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


def _resolve_and_fetch_one(
    cand, claim, period, api_key,
    axis_matcher=None, item_matcher=None, compare_period=None,
):
    """후보 표 1건을 좌표 해소(getMeta)+셀 조회. to_thread 로 동시 호출된다.

    axis_matcher: 규칙+동의어 실패 '분류축'의 폴백(보통 None=결정적; Pass2 에서만 LLM 주입).
    item_matcher: 규칙+동의어 실패 '항목(itmId)'의 폴백(동일 — Pass2 에서만 LLM 주입).
    compare_period: CHANGE_RATE 면 같은 셀 좌표를 이 기준 시점으로 한 번 더 조회(증감 계산용).

    Returns:
        (CellAttempt, matched | None) — matched = (cand, query, cell, compare_cell|None).
        매칭 실패 사유는 CellAttempt.error 에, 항목·분류축은 디버깅용으로 남긴다.
    """
    try:
        query, trace = map_claim_to_cell_query_traced(
            cand.org_id, cand.tbl_id,
            subject=claim.subject, population=claim.population,
            period=period, period_se=claim.period_type, api_key=api_key,
            axis_matcher=axis_matcher,
            item_matcher=item_matcher,
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
    # 증감형 — 같은 셀 좌표를 기준 시점으로 한 번 더 조회(현재−기준 = 증감). 실패는 무시(None).
    compare_cell = None
    if compare_period and compare_period != query.period:
        try:
            compare_cell = fetch_cell_with_retry(
                dataclasses.replace(query, period=compare_period), api_key
            )
        except (KosisError, ValueError):
            compare_cell = None
    return att, (cand, query, cell, compare_cell)


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


def _compare_period(claim: Claim) -> str | None:
    """증감형 claim 의 기준 시점(compare_period)을 KOSIS PRD_DE 로. 비증감/미추출이면 None.

    [2]가 '전년 동월 대비' 같은 비교 기준을 compare_period_value.raw 로 뽑고 [3]이 정규화한다.
    같은 셀 좌표를 이 시점으로 한 번 더 조회해 (현재−기준) 증감을 계산한다([7] compute_change).
    """
    if claim.claim_type != ClaimType.CHANGE_RATE or not claim.compare_period_value:
        return None
    cp = (claim.compare_period_value.llm_value or "").strip()
    if not cp:
        return None
    return _to_kosis_period(claim.period_type, cp)


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


def _to_evidence(
    claim, org_id, tbl_id, query, cell, table_name,
    population_fallback=False, match_source="rule", compare_cell=None,
) -> Evidence:
    """KosisCell → Evidence. unit/period 는 KOSIS 응답값을 그대로 싣는다.

    population_fallback=True 면 요청 모집단을 못 맞춰 전체값으로 대체됐다는 표시.
    match_source 는 모집단 매칭 출처("rule"|"llm").
    compare_cell 은 증감형 기준 시점 셀(있으면 compare_value/compare_period 로 싣는다).
    """
    return Evidence(
        claim_id=claim.claim_id, source="KOSIS",
        subject=claim.subject, unit=cell.unit,
        period_type=claim.period_type, period=cell.period,
        population=claim.population, value=cell.value,
        compare_value=compare_cell.value if compare_cell else None,
        compare_period=compare_cell.period if compare_cell else None,
        kosis_org_id=org_id, kosis_tbl_id=tbl_id, table_name=table_name,
        kosis_item_id=query.itm_id, classification=dict(query.match_filters),
        last_updated=cell.lst_chn_de,
        retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        population_fallback=population_fallback,
        match_source=match_source,
    )


# [Pass3] 값앵커 역매칭 대상(절대형). 증감형은 델타라 슬라이스 스캔 부적합 → 제외.
_REVERSE_TYPES = {ClaimType.ABSOLUTE, ClaimType.VERIFIABLE}
_REVERSE_CAND_CAP = 6  # 후보당 슬라이스 fetch 1콜 → 비용 게이팅


def _reverse_match_one(claim: Claim, cand, period: str, api_key: str):
    """후보표 슬라이스(objL=ALL)에서 값≈claim & 라벨≈population 셀 1개. 단일 명확매치만.

    값 충돌(false-T)을 막으려 '값+라벨 모두 만족하는 셀이 정확히 1개'일 때만 반환한다.
    캐시된 메타로 itmId·축라벨을 알아내 직접 비교(역매칭). 실패/모호는 None.
    """
    from src.kosis.cell import KosisQuery, build_params, to_cell
    from src.kosis.client import call_kosis
    from src.kosis.map_claim_to_cell import _expand, _match_code, _norm
    from src.kosis.metadata import fetch_table_metadata
    from src.numeric.value import parse_claim_value

    parsed = parse_claim_value(claim.value.llm_value)
    if parsed.number is None:
        return None, None
    try:
        meta = fetch_table_metadata(cand.org_id, cand.tbl_id, api_key)  # 캐시 우선
    except KosisError:
        return None, None
    itm = _match_code([(i.itm_id, i.itm_nm) for i in meta.items], claim.subject or "")
    if itm is None:
        return None, None
    nax = len(meta.axes)
    q = KosisQuery(
        org_id=cand.org_id, tbl_id=cand.tbl_id, itm_id=itm,
        period=period, period_se=claim.period_type,
        obj_l1="ALL" if nax >= 1 else "", obj_l2="ALL" if nax >= 2 else "",
        obj_l3="ALL" if nax >= 3 else "", obj_l4="ALL" if nax >= 4 else "",
    )
    try:
        rows = call_kosis(build_params(q, api_key))
    except KosisError:
        return None, None

    target = parsed.number

    def _vmatch(v: float) -> bool:
        for s in (1.0, 1000.0, 0.001):  # 천명↔명 등 스케일 허용
            if abs(v * s - target) <= max(1.0, abs(target) * 0.03):
                return True
        return False

    vm = []
    for r in rows:
        if r.get("PRD_DE") != period or r.get("DT") in (None, ""):
            continue
        try:
            dv = float(r["DT"])
        except (TypeError, ValueError):
            continue
        if _vmatch(dv):
            vm.append(r)
    if not vm:
        return None, None

    # 라벨검증: 집단(population) + subject 의 구분 한정어(산업/연령 등) 로 셀 축라벨을 검증
    # (값 충돌 false-T 차단). '제조업 취업자'처럼 subject 에 박힌 한정어(=objL 값)도 포함.
    pop = claim.population or ""
    cands = {c for c in _expand(pop) if c}
    for tok in (claim.subject or "").split():
        t = _norm(tok)
        if len(t) >= 2:
            cands.add(t)
    if cands:

        def _label_ok(r) -> bool:
            for ax_i, ax in enumerate(meta.axes):
                code = r.get(f"C{ax_i + 1}")
                for c, name in ax.values:
                    if c == code:
                        nn = _norm(name)
                        if nn and (nn in cands or any(x in nn or nn in x for x in cands)):
                            return True
            return False

        vm = [r for r in vm if _label_ok(r)]
    if len(vm) != 1:  # 단일 명확매치만 채택(다중·라벨모호 → 기권)
        return None, None
    return to_cell(vm[0]), q


def _has_value_match(claim: Claim, evidences) -> bool:
    """기존 evidence 중 claim 값과 (스케일 허용) 일치하는 게 있나 — Pass3 발동 게이트."""
    from src.numeric.value import parse_claim_value

    p = parse_claim_value(claim.value.llm_value)
    if p.number is None:
        return False
    t = p.number
    for e in evidences:
        if not isinstance(e.value, (int, float)):
            continue
        for s in (1.0, 1000.0, 0.001):
            if abs(e.value * s - t) <= max(1.0, abs(t) * 0.03):
                return True
    return False


def _reverse_match_candidates(claim: Claim, candidates, period: str, api_key: str):
    """후보들을 역매칭해 (값+라벨) 셀을 evidence 로 만든다(라벨검증=비폴백). 비용상 상위 N개만."""
    out = []
    for cand in candidates[:_REVERSE_CAND_CAP]:
        cell, q = _reverse_match_one(claim, cand, period, api_key)
        if cell is not None:
            out.append(_to_evidence(
                claim, cand.org_id, cand.tbl_id, q, cell, cand.tbl_nm,
                population_fallback=False, match_source="reverse",
            ))
    return out


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
