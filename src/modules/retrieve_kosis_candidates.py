from __future__ import annotations

import asyncio
import json
import logging
import time

from src.kosis import KosisError, SearchHit, search_tables_many
from src.kosis.keyword_expand import expand_subject
from src.llm.client import LlmError
from src.llm.model_presets import EXPAND_KEYWORDS
from src.observability.tracing import traced_chat
from src.prompts.prompts import EXPAND_KEYWORDS_SYSTEM, EXPAND_KEYWORDS_USER
from src.schemas.runtime import (
    Claim,
    ClaimAnalysis,
    KosisCandidate,
    KosisQuery,
    KosisSearch,
    MasterSchema,
)

logger = logging.getLogger(__name__)

TOP_N = 10            # claim별 후보 통계표 상위 N개(병합·재랭킹 후 절단)
MAX_VARIANTS = 4      # subject당 검색 키워드 변형 상한 — KOSIS 호출 증폭 가드
_SEARCH_API = "statisticsSearch.do"
_DATA_API = "statisticsData.do"

_EXPAND_SCHEMA = {
    "type": "object",
    "properties": {"keywords": {"type": "array", "items": {"type": "string"}}},
    "required": ["keywords"],
}


"""
표 찾기(statisticsSearch.do) — subject 변형 다중 검색 → 병합·재랭킹.
"""


class RetrieveKosisCandidatesError(Exception):
    """KOSIS 후보 통계표 검색 실패."""


async def retrieve_kosis_candidates(master_schema: MasterSchema) -> None:
    """
    [4] Retrieve KOSIS Candidates

    Input:  master_schema.claims         # subject / unit / period 등
    Output: master_schema.analysis       # claim별 ClaimAnalysis
              - kosis_search : 통합검색 로그(사용 키워드 변형 포함)
              - candidates   : 병합·재랭킹 후 상위 TOP_N 후보 통계표
              - kosis_query  : placeholder ([5]에서 채움)

    claim별 subject 를 여러 검색어 변형(원본·핵심명사·동의어·상위어; 룰 결정적,
    빈약 시 LLM 폴백)으로 통합검색(statisticsSearch.do)해 결과를 tbl_id 기준 병합·
    dedup 하고, 시군구·국제표를 후순위로 재랭킹한 뒤 상위 TOP_N 을 후보로 둔다.
    '가장 적합한 1개' 선정은 이후 단계의 몫이라 RANK 1위만 임시 selected 로 둔다.

    한 claim 의 검색 실패(KosisError/ValueError)는 success=0 으로 기록하고 계속 진행.
    """
    master_schema.analysis = list(
        await asyncio.gather(
            *(_search_one_claim(claim) for claim in master_schema.claims)
        )
    )


def _rerank_hits(hits: list[SearchHit]) -> list[SearchHit]:
    """시군구통계·국제통계(DT_2*)를 후순위로 밀고 그 외 RANK 순서 유지(stable sort).

    전국(계) 표가 시군구·국제표에 밀려 TOP_N 밖으로 잘리는 것을 막는다(오버페치 후 절단).
    """
    def _score(h: SearchHit) -> int:
        if h.stat_nm == "시군구통계":
            return 2
        if h.tbl_id.startswith("DT_2"):
            return 1
        return 0
    return sorted(hits, key=_score)


def _merge_dedup(variants: list[str], hits_by_kw: dict[str, list[SearchHit]]) -> list[SearchHit]:
    """변형 순서대로 검색 결과를 union, tbl_id 기준 dedup(첫 등장 유지)."""
    seen: set[str] = set()
    pool: list[SearchHit] = []
    for kw in variants:
        for h in hits_by_kw.get(kw, []):
            if h.tbl_id and h.tbl_id not in seen:
                seen.add(h.tbl_id)
                pool.append(h)
    return pool


def _llm_expand_keywords(subject: str) -> list[str]:
    """룰 변형이 빈약할 때만 호출하는 LLM 폴백 — KOSIS 검색어 후보 목록.

    닫힌 형식(JSON 배열)을 structured outputs 로 강제. 실패/빈 응답은 [] (결정적 폴백).
    """
    messages = [
        {"role": "system", "content": EXPAND_KEYWORDS_SYSTEM},
        {"role": "user", "content": EXPAND_KEYWORDS_USER.format(subject=subject)},
    ]
    try:
        resp = traced_chat(
            model_alias=EXPAND_KEYWORDS.model_alias,
            model_name=EXPAND_KEYWORDS.model_name,
            messages=messages,
            max_tokens=EXPAND_KEYWORDS.max_tokens,
            temperature=EXPAND_KEYWORDS.temperature,
            json_structure=_EXPAND_SCHEMA,
            trace_name="retrieve_kosis_candidates:expand_keywords",
        )
    except (LlmError, AttributeError) as exc:
        logger.warning("키워드 확장 LLM 폴백 실패(%s): %s", subject, exc)
        return []
    try:
        data = json.loads(resp.text.strip())
    except (json.JSONDecodeError, AttributeError):
        return []
    return ["".join(str(k).split()) for k in (data.get("keywords") or []) if k]


async def _search_one_claim(claim: Claim) -> ClaimAnalysis:
    """claim 1건 → 변형 다중 검색 → 병합·재랭킹 → ClaimAnalysis(후보 풀).

    룰 변형 검색이 0건일 때만 LLM 폴백으로 검색어를 보강해 재검색한다(진짜 '미스'
    한정 → LLM 호출·비결정성·KOSIS 호출을 최소화).
    """
    subject = claim.subject or ""
    variants = expand_subject(subject, max_variants=MAX_VARIANTS)
    t0 = time.perf_counter()

    if not variants:
        return _analysis(claim.claim_id, "", variants, hits=[], success=1,
                         error_msg=None, duration_ms=_ms_since(t0))

    try:
        hits_by_kw = await asyncio.to_thread(search_tables_many, variants, top_n=TOP_N)
    except (KosisError, ValueError) as exc:
        return _analysis(claim.claim_id, variants[0], variants, hits=[], success=0,
                         error_msg=str(exc), duration_ms=_ms_since(t0))

    pool = _rerank_hits(_merge_dedup(variants, hits_by_kw))[:TOP_N]
    used = list(variants)

    # 룰 검색 0건 = 진짜 미스 → LLM 폴백 검색어로 재검색.
    if not pool:
        extra = [e for e in _dedup_keep_order(await asyncio.to_thread(_llm_expand_keywords, subject))
                 if e not in set(variants)][:MAX_VARIANTS]
        if extra:
            try:
                more = await asyncio.to_thread(search_tables_many, extra, top_n=TOP_N)
                used = variants + extra
                pool = _rerank_hits(_merge_dedup(used, {**hits_by_kw, **more}))[:TOP_N]
            except (KosisError, ValueError):
                pass

    return _analysis(claim.claim_id, used[0], used, hits=pool, success=1,
                     error_msg=None, duration_ms=_ms_since(t0))


def _dedup_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _analysis(
    claim_id: str,
    keyword: str,
    variants: list[str],
    *,
    hits: list[SearchHit],
    success: int,
    error_msg: str | None,
    duration_ms: int,
) -> ClaimAnalysis:
    # 선정은 이후 단계의 몫. RANK 1위를 임시 선정값으로 둬 [5]가 동작하게 한다.
    top = hits[0] if hits else None
    return ClaimAnalysis(
        claim_id=claim_id,
        kosis_search=KosisSearch(
            api=_SEARCH_API,
            query=keyword,
            params=_params_log(variants),
            hits=len(hits),
            selected_tbl_id=top.tbl_id if top else None,
            selected_tbl_name=top.tbl_nm if top else None,
            success=success,
            error_msg=error_msg,
            duration_ms=duration_ms,
        ),
        candidates=[_candidate(h) for h in hits],
        kosis_query=_placeholder_query(),
    )


def _candidate(hit: SearchHit) -> KosisCandidate:
    return KosisCandidate(
        org_id=hit.org_id,
        tbl_id=hit.tbl_id,
        tbl_nm=hit.tbl_nm,
        org_nm=hit.org_nm,
        stat_nm=hit.stat_nm,
        prd_de=hit.prd_de,
    )


def _placeholder_query() -> KosisQuery:
    """[5] fetch_kosis_data 가 채울 자리. 미조회 상태(success=0)."""
    return KosisQuery(
        api=_DATA_API,
        tbl_id="",
        params="",
        rows_returned=0,
        success=0,
        duration_ms=0,
    )


def _params_log(variants: list[str]) -> str:
    """검색 호출 파라미터를 로그용 JSON 문자열로. apiKey 는 절대 포함하지 않는다."""
    return json.dumps(
        {
            "method": "getList",
            "searchNm": variants[0] if variants else "",
            "variants": variants,
            "startCount": "1",
            "resultCount": str(TOP_N),
            "sort": "RANK",
            "format": "json",
        },
        ensure_ascii=False,
    )


def _ms_since(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
