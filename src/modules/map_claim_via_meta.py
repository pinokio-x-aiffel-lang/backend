"""[4+5 대안 경로] 검색 → 메타 직접 판독 → 표·코드 LLM 선택 → 셀 조회.

기존 [4] retrieve_kosis_candidates(트리 드릴다운) + [5] fetch_kosis_data(규칙+LLM 폴백)와
**병행**하는 단일 경로다. 사람이 KOSIS 표를 열어 항목·분류축을 직접 보고 고르듯,
후보 표들의 실제 구조(itmId·objL 코드)를 LLM 에게 보여주고 한 번에 표+좌표를 고르게 한다.

절차·휴리스틱의 단일 진실 명세: `.claude/skills/kosis-lookup/SKILL.md`.
LLM 은 traced_chat(=LlmCaller 경유, Langfuse 기록)만, 파라미터는 ModelPreset(SELECT_KOSIS_CELL)만.

기존 Pipeline.run() 은 건드리지 않는다 — A/B 비교용으로 독립 호출/대체 가능하게 같은
MasterSchema.analysis/evidences 스키마를 채운다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone

from src.kosis import (
    KosisError,
    TableMetadata,
    call_kosis,
    fetch_table_metadata,
    resolve_api_key,
    search_tables,
)
from src.kosis.search import SearchHit
from src.llm.client import LlmError
import os

from src.llm.model_presets import GEN_KOSIS_KEYWORDS, SELECT_KOSIS_CELL, SELECT_KOSIS_CELL_CLAUDE
from src.observability.tracing import traced_chat
from src.prompts.prompts import (
    GEN_KOSIS_KEYWORDS_SYSTEM,
    GEN_KOSIS_KEYWORDS_USER,
    SELECT_KOSIS_CELL_SYSTEM,
    SELECT_KOSIS_CELL_USER,
)
from src.schemas.runtime import (
    Claim,
    ClaimAnalysis,
    Evidence,
    KosisCandidate,
    KosisQuery,
    KosisSearch,
    MasterSchema,
)

logger = logging.getLogger("kosis")

_SEARCH_API = "statisticsSearch.do"
_DATA_API = "statisticsParameterData.do"

KEYWORD_TOP_N = 30   # 검색 후보 풀(넓게 받아 재랭킹으로 거른다)
META_TOP_K = 8       # 메타까지 읽어 LLM 보기로 줄 후보 수(토큰·지연 균형)
_ITEMS_CAP = 30      # 보기 항목 상한
_AXIS_VALS_CAP = 40  # 보기 축값 상한

# 국가 한정 접두어 — KOSIS 키워드 오염 → 제거.
_SUBJECT_DROP_PREFIXES = ("한국 ", "한국의 ", "우리나라 ", "우리나라의 ")
# 모집단 한정 접두어 — 검색을 시도/국제 변형으로 오염시켜 전국 핵심표를 밀어낸다.
# (모집단은 분류축으로 따로 매핑하므로 키워드에선 뺀다. 예: '청년 실업률'→'실업률')
_POP_DROP_PREFIXES = (
    "청년층 ", "청년 ", "고령층 ", "고령 ", "노인 ", "여성 ", "남성 ",
    "중장년 ", "장년 ", "전체 ",
)
# 검색 노이즈 접미사 — 의미는 항목/연산이 담당. 검색어에선 제거(예: '취업자 수'→'취업자').
_SUBJECT_DROP_SUFFIXES = (
    " 상승률", " 증감률", " 등락률", " 증감", " 수", " 비중", " 규모", " 수치",
)
# 재랭킹(조사명 anchored): 내가 KOSIS 에서 표를 고를 때 1순위 신호는 '조사명'이다.
# 국제기구 집계는 즉시 버리고(IMF/OECD/UN/World Bank/ILO/국제통계), 지역 단위 조사는
# 디모트(지역별고용조사/e-지방지표/시도통계/시군구), 국내 정식 전국조사를 최우선한다.
_INTL_TOKENS = ("OECD", "IMF", "UN ", "World", "ILO", "국제", "신남방", "신북방",
                "북한", "이민자")
_REGIONAL_TOKENS = ("시도", "시군구", "시/군/구", "지역별", "지방", "행정구역",
                    "광역", "근무지기준")
# claim.period_type → KOSIS prdSe (반기 S→H).
_PRDSE_API = {"Y": "Y", "M": "M", "Q": "Q", "S": "H", "D": "D"}
# 항목명이 '이미 변화율'인지 — YoY 직접계산 스킵 판별.
_RATE_TOKENS = ("전년", "전월", "증감", "등락", "상승률", "감소율", "변화율")

# LLM 응답 구조(structured outputs): 표·항목·축코드·기권.
_SELECT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "tbl_id": {"type": ["string", "null"]},
        "itm_id": {"type": ["string", "null"]},
        "axis_codes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "obj_id": {"type": "string"},
                    "code": {"type": "string"},
                },
                "required": ["obj_id", "code"],
            },
        },
        "abstain": {"type": "boolean"},
    },
    "required": ["tbl_id", "itm_id", "axis_codes", "abstain"],
}


# LLM 키워드 생성 응답 구조.
_KEYWORDS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"keywords": {"type": "array", "items": {"type": "string"}}},
    "required": ["keywords"],
}


class MapClaimViaMetaError(Exception):
    """검색→메타 경로 실패."""


# ── 파이프라인 진입점 ─────────────────────────────────────────────────────────
async def map_claim_via_meta(master_schema: MasterSchema) -> None:
    """[4+5 대안] claim 별 검색→메타→선택→조회로 analysis/evidences 를 채운다.

    한 claim 실패(KosisError/ValueError/LlmError)는 success=0 으로 기록하고 계속.
    그 외 예외만 raise → runner.
    """
    api_key = resolve_api_key()
    master_schema.analysis = list(
        await asyncio.gather(
            *(_resolve_one(claim, api_key) for claim in master_schema.claims)
        )
    )


async def _resolve_one(claim: Claim, api_key: str) -> ClaimAnalysis:
    """claim 1건 → ClaimAnalysis(후보·선정 표·evidence)."""
    keyword = _preprocess_subject(claim.subject or "")
    t0 = time.perf_counter()

    # [1] LLM 으로 검색 키워드 2~4개 생성(범주어→부모 차원어). 항상 정제 keyword 도 포함.
    try:
        kws = await asyncio.to_thread(_gen_keywords, claim, keyword)
    except LlmError:
        kws = []
    # LLM 이 만든 차원 키워드(예 '산업별 취업자','소비자물가지수')를 앞에 — 정제 주제어는
    # 범주어 노이즈(제조업→외국인 등)가 많아 폴백으로 뒤에 둔다. (내 조회 과정 반영)
    keywords = _dedup([*kws, keyword])

    # [2] 키워드별 검색 후 후보 병합(tbl_id 기준 dedup, 등장 순 보존).
    try:
        hits = await _search_merge(keywords)
    except (KosisError, ValueError) as exc:
        return _analysis(claim, keyword, [], None, None, success=0,
                         error_msg=str(exc), duration_ms=_ms(t0))
    if not hits:
        return _analysis(claim, keyword, [], None, None, success=0,
                         error_msg="검색 결과 0건", duration_ms=_ms(t0))

    # 기간 미수록 표(구버전 등) 제외 → 전국 핵심표 우선 재랭킹 → 상위 K개 메타 조회.
    period_for_filter = _to_kosis_period(claim.period_type, claim.period_value.llm_value)
    covering = [h for h in hits if _covers_period(h, period_for_filter)]
    hits = _rerank_national(covering or hits, claim)
    top = hits[:META_TOP_K]
    metas = await asyncio.gather(
        *(asyncio.to_thread(_safe_meta, h.org_id, h.tbl_id, api_key) for h in top)
    )
    pairs = [(h, m) for h, m in zip(top, metas) if m is not None]
    if not pairs:
        return _analysis(claim, keyword, hits, None, None, success=0,
                         error_msg="후보 메타 조회 전부 실패", duration_ms=_ms(t0))

    # LLM 이 표+항목+축코드 선택.
    try:
        sel = await asyncio.to_thread(_select_cell_llm, claim, keyword, pairs)
    except LlmError as exc:
        return _analysis(claim, keyword, hits, None, None, success=0,
                         error_msg=f"LLM 선택 실패: {exc}", duration_ms=_ms(t0))
    if sel is None or sel.get("abstain") or not sel.get("tbl_id"):
        return _analysis(claim, keyword, hits, None, None, success=0,
                         error_msg="LLM 기권(적합 표 없음)", duration_ms=_ms(t0))

    chosen = next((p for p in pairs if p[0].tbl_id == sel["tbl_id"]), None)
    if chosen is None:
        return _analysis(claim, keyword, hits, None, None, success=0,
                         error_msg=f"LLM 이 보기 밖 tbl_id 반환: {sel['tbl_id']}",
                         duration_ms=_ms(t0))

    hit, meta = chosen
    try:
        evidence, query = await asyncio.to_thread(
            _fetch_selected_cell, claim, hit, meta, sel, api_key
        )
    except (KosisError, ValueError) as exc:
        return _analysis(claim, keyword, hits, hit, None, success=0,
                         error_msg=f"셀 조회 실패: {exc}", duration_ms=_ms(t0))
    if evidence is None:
        return _analysis(claim, keyword, hits, hit, None, success=0,
                         error_msg="셀 매칭 0건(시점/분류 불일치)", duration_ms=_ms(t0))

    return _analysis(claim, keyword, hits, hit, (evidence, query),
                     success=1, error_msg=None, duration_ms=_ms(t0))


# ── 키워드 생성·검색 병합 ─────────────────────────────────────────────────────
def _gen_keywords(claim: Claim, keyword: str) -> list[str]:
    """LLM 으로 KOSIS 검색 키워드 2~4개 생성(범주어→부모 차원어). 실패/형식오류는 []."""
    messages = [
        {"role": "system", "content": GEN_KOSIS_KEYWORDS_SYSTEM},
        {"role": "user", "content": GEN_KOSIS_KEYWORDS_USER.format(
            subject=keyword or claim.subject, population=claim.population,
            unit=claim.unit, claim_type=claim.claim_type.value,
        )},
    ]
    resp = traced_chat(
        model_alias=GEN_KOSIS_KEYWORDS.model_alias,
        model_name=GEN_KOSIS_KEYWORDS.model_name,
        messages=messages,
        max_tokens=GEN_KOSIS_KEYWORDS.max_tokens,
        temperature=GEN_KOSIS_KEYWORDS.temperature,
        json_structure=_KEYWORDS_SCHEMA,
        trace_name="map_claim_via_meta:keywords",
    )
    try:
        data = json.loads(resp.text.strip())
    except (json.JSONDecodeError, AttributeError):
        return []
    kws = data.get("keywords")
    return [str(k).strip() for k in kws if str(k).strip()] if isinstance(kws, list) else []


async def _search_merge(keywords: list[str]) -> list[SearchHit]:
    """키워드 순서대로(가장 구체적/핵심적인 것 먼저) 검색 결과를 이어붙여 dedup 병합.

    keywords 는 best-first(부모 차원 키워드가 앞). 앞 키워드의 상위표가 먼저 자리잡아
    이후 tier 정렬에서도 우위를 갖는다 — 내 조회 과정(구체 키워드부터 훑기) 반영.
    """
    results = await asyncio.gather(
        *(asyncio.to_thread(search_tables, kw, top_n=KEYWORD_TOP_N) for kw in keywords),
        return_exceptions=True,
    )
    merged: dict[str, SearchHit] = {}
    for res in results:
        if isinstance(res, Exception):
            continue
        for h in res:
            merged.setdefault(h.tbl_id, h)
    return list(merged.values())


def _dedup(items: list[str]) -> list[str]:
    """빈 문자열 제거 + 순서 보존 dedup."""
    out: list[str] = []
    for x in items:
        x = (x or "").strip()
        if x and x not in out:
            out.append(x)
    return out


# ── LLM 선택 ─────────────────────────────────────────────────────────────────
def _select_cell_llm(
    claim: Claim, keyword: str, pairs: list[tuple[SearchHit, TableMetadata]]
) -> dict | None:
    """후보 표 메타를 보여주고 표+itmId+축코드를 고른다. 실패/형식오류는 None."""
    tables = "\n\n".join(_meta_block(h, m) for h, m in pairs)
    period = f"{claim.period_type}:{claim.period_value.llm_value}"
    messages = [
        {"role": "system", "content": SELECT_KOSIS_CELL_SYSTEM},
        {"role": "user", "content": SELECT_KOSIS_CELL_USER.format(
            subject=keyword or claim.subject, population=claim.population,
            unit=claim.unit, period=period, value=claim.value.llm_value,
            claim_type=claim.claim_type.value, tables=tables,
        )},
    ]
    _preset = SELECT_KOSIS_CELL_CLAUDE if os.environ.get("KOSIS_SELECT_MODEL") == "claude" else SELECT_KOSIS_CELL
    resp = traced_chat(
        model_alias=_preset.model_alias,
        model_name=_preset.model_name,
        messages=messages,
        max_tokens=_preset.max_tokens,
        temperature=_preset.temperature,
        json_structure=_SELECT_SCHEMA,
        trace_name="map_claim_via_meta:select",
    )
    try:
        return json.loads(resp.text.strip())
    except (json.JSONDecodeError, AttributeError):
        return None


def _meta_block(hit: SearchHit, meta: TableMetadata) -> str:
    """후보 표 1개를 LLM 보기 텍스트로. 항목·축값은 상한으로 자른다."""
    items = "; ".join(
        f"{it.itm_id}={it.itm_nm}" + (f"({it.unit})" if it.unit else "")
        for it in meta.items[:_ITEMS_CAP]
    ) or "(항목 없음)"
    axes_lines = []
    for ax in meta.axes:
        vals = "; ".join(f"{c}={n}" for c, n in ax.values[:_AXIS_VALS_CAP])
        axes_lines.append(f"  축[{ax.name}/{ax.obj_id}]: {vals}")
    prd = ",".join(p.se_code or p.se_label for p in meta.periods) or "?"
    head = f"[tbl_id={hit.tbl_id} | org={hit.org_id}] {hit.tbl_nm} ({hit.stat_nm}) | 주기:{prd}"
    return "\n".join([head, f"  항목: {items}", *axes_lines])


# ── 셀 조회 ──────────────────────────────────────────────────────────────────
def _fetch_selected_cell(
    claim: Claim, hit: SearchHit, meta: TableMetadata, sel: dict, api_key: str
) -> tuple[Evidence | None, KosisQuery | None]:
    """선택된 표+itmId+축코드로 셀을 조회한다.

    objL 레벨을 표 축 수 기준 ±조정하며 전 행을 받고(숨은 C1축 대응),
    응답 행에서 itmId + 축값(이름) 일치 행을 고른다(위치 독립적 이름 매칭).
    change_rate 인데 지수 항목이면 전년 동기 셀로 YoY 를 직접 계산한다.
    """
    period = _to_kosis_period(claim.period_type, claim.period_value.llm_value)
    prd_se = _PRDSE_API.get(claim.period_type, claim.period_type)
    itm_id = sel.get("itm_id") or "ALL"

    # 고른 축코드 → 이름(매칭 키). 코드는 메타에서 이름으로 해석.
    chosen_names = _codes_to_names(meta, sel.get("axis_codes") or [])
    rows = _fetch_rows(hit.org_id, hit.tbl_id, itm_id, period, prd_se,
                       len(meta.axes), api_key)
    row = _pick_row(rows, itm_id, chosen_names)
    if row is None:
        return None, None

    value = _to_float(row.get("DT"))
    if value is None:
        return None, None
    unit = row.get("UNIT_NM", "")

    # change_rate + 지수 항목 → 전년 동기로 YoY 직접 계산.
    item_name = _item_name(meta, itm_id)
    if claim.claim_type.value == "change_rate" and not _is_rate_item(item_name):
        prev = _yoy_prev_period(period)
        if prev:
            prev_rows = _fetch_rows(hit.org_id, hit.tbl_id, itm_id, prev, prd_se,
                                    len(meta.axes), api_key)
            prev_row = _pick_row(prev_rows, itm_id, chosen_names)
            prev_val = _to_float(prev_row.get("DT")) if prev_row else None
            if prev_val not in (None, 0):
                value = round((value / prev_val - 1) * 100, 4)
                unit = "%"

    query = KosisQuery(
        api=_DATA_API, tbl_id=hit.tbl_id,
        params=json.dumps({
            "orgId": hit.org_id, "tblId": hit.tbl_id, "itmId": itm_id,
            "prdSe": prd_se, "prd": period,
            "axis_codes": sel.get("axis_codes"),
        }, ensure_ascii=False),
        rows_returned=len(rows), success=1, duration_ms=0,
    )
    evidence = Evidence(
        claim_id=claim.claim_id, source="KOSIS",
        subject=claim.subject, unit=unit,
        period_type=claim.period_type, period=str(row.get("PRD_DE", period)),
        population=claim.population,
        value=value,
        kosis_org_id=hit.org_id, kosis_tbl_id=hit.tbl_id, table_name=hit.tbl_nm,
        kosis_item_id=itm_id,
        classification={a["obj_id"]: a["code"] for a in (sel.get("axis_codes") or [])},
        last_updated=row.get("LST_CHN_DE"),
        retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        match_source="llm",
    )
    return evidence, query


def _fetch_rows(org: str, tbl: str, itm: str, period: str, prd_se: str,
                n_axes: int, api_key: str) -> list[dict]:
    """objL 레벨 수를 ±조정하며 해당 기간 전 행을 받는다(숨은 C1축 대응).

    빈 objL → error 21, 부족 → error 20, 잘못된 objL 수 → error 30(데이터 없음)도 가능.
    메타 축 수가 데이터와 다를 수 있어 n, n+1, n+2, n-1 순으로 시도(첫 성공 채택).
    20/21/30 은 레벨 수 문제일 수 있어 다음 레벨로 넘어가고, 그 외 오류만 raise.
    전 레벨 실패면 [].
    """
    base = {
        "method": "getList", "apiKey": api_key, "itmId": itm,
        "prdSe": prd_se, "startPrdDe": period, "endPrdDe": period,
        "orgId": org, "tblId": tbl,
    }
    retryable = ("20:", "21:", "30:")
    for n in (max(1, n_axes), n_axes + 1, n_axes + 2, max(1, n_axes - 1)):
        params = dict(base, **{f"objL{i}": "ALL" for i in range(1, n + 1)})
        try:
            rows = call_kosis(params)
            if rows:
                return rows  # 빈 응답이면 다음 레벨도 시도
        except KosisError as exc:
            if not str(exc).startswith(retryable):
                raise
    return []


# 미지정 축의 기본값 — '전체/합계'를 뜻하는 분류값 이름.
_TOTAL_NAMES = ("계", "소계", "전체", "합계")


def _pick_row(rows: list[dict], itm_id: str, chosen_names: list[str]) -> dict | None:
    """itmId 일치 + 고른 축값(이름) 매칭 행. 위치 독립(이름 매칭).

    LLM 이 축을 일부만 지정해도(예: 연령만 고르고 교육정도 누락) 동작하도록,
    동점일 때 **미지정 축이 '계/합계'인 행을 우선**한다(전체값 기본). chosen_names 가
    비면 모든 축이 '계'인 행(없으면 첫 행)을 고른다.
    """
    cand = [
        r for r in rows
        if isinstance(r, dict) and (itm_id in ("ALL", None) or r.get("ITM_ID") == itm_id)
    ]
    if not cand:
        return None

    def names_of(r: dict) -> list[str]:
        return [str(r.get(f"C{i}_NM")) for i in range(1, 5) if r.get(f"C{i}_NM")]

    def total_extras(r: dict, matched: set[str]) -> int:
        # 고른 값과 무관한 나머지 축이 '계'류이면 점수↑(전체값 기본 매칭).
        return sum(1 for nm in names_of(r) if nm not in matched and
                   any(t == nm or t in nm for t in _TOTAL_NAMES))

    if not chosen_names:
        return max(cand, key=lambda r: total_extras(r, set()), default=cand[0])

    best, best_key = None, (-1, -1)
    for r in cand:
        names = set(names_of(r))
        matched = {nm for nm in chosen_names if nm in names}
        key = (len(matched), total_extras(r, matched))
        if key > best_key:
            best, best_key = r, key
    # 고른 축이 하나도 안 맞으면 매칭 실패로 본다.
    return best if best_key[0] > 0 else None


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────
def _safe_meta(org: str, tbl: str, api_key: str) -> TableMetadata | None:
    try:
        return fetch_table_metadata(org, tbl, api_key)
    except (KosisError, ValueError) as exc:
        logger.warning("KOSIS 메타 실패 tbl=%s: %s", tbl, exc)
        return None


def _codes_to_names(meta: TableMetadata, axis_codes: list[dict]) -> list[str]:
    """고른 {obj_id, code} 들을 메타 축에서 이름으로 해석.

    LLM 이 obj_id 를 환각하는 경우(예 '지수종류')가 있어, obj_id 로 못 찾으면
    code 를 **전체 축**에서 탐색한다(위치 독립). 그래도 없으면 코드 그대로.
    """
    by_obj = {ax.obj_id: dict(ax.values) for ax in meta.axes}
    all_codes: dict[str, str] = {}
    for ax in meta.axes:
        for c, n in ax.values:
            all_codes.setdefault(c, n)
    names = []
    for a in axis_codes:
        code = str(a.get("code"))
        name = by_obj.get(str(a.get("obj_id")), {}).get(code) or all_codes.get(code, code)
        names.append(name)
    return names


def _item_name(meta: TableMetadata, itm_id: str) -> str:
    return next((it.itm_nm for it in meta.items if it.itm_id == itm_id), "")


def _is_rate_item(name: str) -> bool:
    return any(tok in (name or "") for tok in _RATE_TOKENS)


def _to_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _yoy_prev_period(period: str) -> str | None:
    """전년 동기 — 연도 4자리만 −1, 월/분기 뒤 2자리 유지. 파싱불가 None."""
    p = str(period or "")
    return str(int(p[:4]) - 1) + p[4:] if len(p) >= 4 and p[:4].isdigit() else None


def _to_kosis_period(period_type: str, raw: str) -> str:
    """claim 시점값 → KOSIS PRD_DE (Y=YYYY, M/Q/S=YYYYNN)."""
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


def _preprocess_subject(subject: str) -> str:
    """검색어 정제: 국가·모집단 접두어와 노이즈 접미어 제거(검색 recall 향상).

    모집단(청년 등)·연산(상승률 등)은 분류축/항목이 담당하므로 검색어에선 뺀다.
    """
    s = subject.strip()
    for prefix in _SUBJECT_DROP_PREFIXES + _POP_DROP_PREFIXES:
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
            break
    for suffix in _SUBJECT_DROP_SUFFIXES:
        if s.endswith(suffix) and len(s) > len(suffix):
            s = s[: -len(suffix)].strip()
            break
    return s


def _covers_period(hit: SearchHit, period: str) -> bool:
    """표 수록기간(STRT~END)이 claim 연도를 포함하는가. 정보 없으면 보수적으로 True.

    구버전 표(예 ~2024)가 최신 claim(2025~)을 밀어내지 않게 후보에서 거른다.
    연 단위 비교(시작연≤claim연≤종료연)면 충분 — 표마다 STRT 형식이 제각각이라.
    """
    raw = hit.raw or {}
    claim_y = _year(period)
    if claim_y is None:
        return True
    start_y = _year(str(raw.get("STRT_PRD_DE", "")))
    end_y = _year(str(raw.get("END_PRD_DE", "")))
    if start_y and claim_y < start_y:
        return False
    if end_y and claim_y > end_y:
        return False
    return True


def _year(s: str) -> int | None:
    m = re.match(r"\s*(\d{4})", str(s or ""))
    return int(m.group(1)) if m else None


def _survey_tier(hit: SearchHit, regional_claim: bool) -> int:
    """조사명 anchored 티어: 0=국내 정식 전국조사, 1=지역 단위 조사, 2=국제기구 집계.

    내가 표를 고를 때 가장 먼저 보는 신호(조사명/표명)를 그대로 코드화한다.
    """
    text = f"{hit.tbl_nm} {hit.stat_nm}"
    if any(t in text for t in _INTL_TOKENS) or hit.tbl_id.startswith("DT_2"):
        return 2  # IMF/OECD/UN/World Bank/국제통계 — 즉시 버림
    if not regional_claim and (
        any(t in text for t in _REGIONAL_TOKENS) or hit.tbl_id.startswith("INH_")
    ):
        return 1  # 지역별고용조사/시도·시군구/지방지표 — 디모트
    return 0      # 경제활동인구조사·소비자물가조사·인구동향조사·장래인구추계 등


def _rerank_national(hits: list[SearchHit], claim: Claim) -> list[SearchHit]:
    """조사명 티어로 안정 정렬(동점은 입력 순서=키워드·RANK 우선 유지).

    claim 모집단이 지역을 명시하면 지역조사를 디모트하지 않는다.
    """
    regional_claim = any(t in (claim.population or "") for t in ("시도", "지역", "시군구"))
    return sorted(hits, key=lambda h: _survey_tier(h, regional_claim))


def _analysis(
    claim: Claim, keyword: str, hits: list[SearchHit], selected: SearchHit | None,
    matched: tuple[Evidence, KosisQuery] | None, *,
    success: int, error_msg: str | None, duration_ms: int,
) -> ClaimAnalysis:
    """검색→메타 경로 결과를 ClaimAnalysis 로 조립([6]~ 가 그대로 소비 가능)."""
    evidence, query = (matched if matched else (None, None))
    return ClaimAnalysis(
        claim_id=claim.claim_id,
        kosis_search=KosisSearch(
            api=_SEARCH_API, query=keyword,
            params=json.dumps({"strategy": "meta-readout", "top_k": META_TOP_K},
                              ensure_ascii=False),
            hits=len(hits),
            selected_tbl_id=selected.tbl_id if selected else None,
            selected_tbl_name=selected.tbl_nm if selected else None,
            success=success, error_msg=error_msg, duration_ms=duration_ms,
        ),
        candidates=[
            KosisCandidate(org_id=h.org_id, tbl_id=h.tbl_id, tbl_nm=h.tbl_nm,
                           org_nm=h.org_nm, stat_nm=h.stat_nm, prd_de=h.prd_de)
            for h in hits
        ],
        kosis_query=query or KosisQuery(
            api=_DATA_API, tbl_id="", params="", rows_returned=0,
            success=0, error_msg=error_msg, duration_ms=0,
        ),
        evidences=[evidence] if evidence else [],
    )


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
