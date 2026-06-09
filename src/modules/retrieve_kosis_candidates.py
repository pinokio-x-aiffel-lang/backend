from __future__ import annotations

import asyncio
import json
import time

from src.kosis import KosisError, SearchHit, search_tables
from src.schemas.runtime import (
    Claim,
    ClaimAnalysis,
    KosisCandidate,
    KosisQuery,
    KosisSearch,
    MasterSchema,
)

TOP_N = 10  # claim별 후보 통계표 상위 N개
_SEARCH_API = "statisticsSearch.do"
_DATA_API = "statisticsData.do"

# subject 앞에 붙는 국가 한정어는 KOSIS 키워드 오염 원인 → 제거
_SUBJECT_DROP_PREFIXES = ("한국 ", "한국의 ", "우리나라 ", "우리나라의 ")


"""
표 찾기(statisticsSearch.do, 키워드)
"""


class RetrieveKosisCandidatesError(Exception):
    """KOSIS 후보 통계표 검색 실패."""


async def retrieve_kosis_candidates(master_schema: MasterSchema) -> None:
    """
    [4] Retrieve KOSIS Candidates

    Input:
        master_schema.claims         # subject / unit / period 등

    Output:
        master_schema.analysis       # claim별 ClaimAnalysis 초기화
                                      #   - kosis_search : 통합검색 호출 로그
                                      #   - candidates   : 상위 TOP_N개 후보 통계표
                                      #   - kosis_query  : placeholder ([5]에서 채움)

    Responsibility:
        claim별 subject 로 KOSIS 통합검색(statisticsSearch.do)을 호출해
        후보 통계표 상위 TOP_N개를 수집, master_schema.analysis 를 초기화한다.
        '가장 적합한 1개' 선정은 이후 단계의 몫이라 여기선 수집만 하고,
        [5] fetch_kosis_data 가 동작하도록 RANK 1위를 selected_tbl_id 에 임시로 둔다.

        한 claim 의 검색 실패(KosisError/ValueError)는 success=0 + error_msg 로
        기록하고 계속 진행한다(한 건이 전체 파이프라인을 막지 않게). 그 외
        예기치 못한 예외만 raise → runner 가 StepEvent(error) 로 처리.
    """
    # search_tables 는 동기 requests 기반이라 이벤트 루프를 막지 않게 to_thread 로
    # 위임한다(_search_one_claim 내부). claim 간 검색은 gather 로 동시 호출 —
    # rate limit 은 공유 client 가 sliding-window lock 으로 1000/min 이하 강제(동시 안전).
    # gather 는 입력 순서를 보존하므로 analysis 순서 == claims 순서.
    master_schema.analysis = list(
        await asyncio.gather(
            *(_search_one_claim(claim) for claim in master_schema.claims)
        )
    )


def _preprocess_subject(subject: str) -> str:
    """KOSIS 검색어 전처리: 국가 한정 접두어 제거 + 공백 제거."""
    s = subject.strip()
    for prefix in _SUBJECT_DROP_PREFIXES:
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return "".join(s.split())


def _rerank_hits(hits: list[SearchHit]) -> list[SearchHit]:
    """시군구통계·국제통계(DT_2*)를 후순위로 밀고 원래 RANK 순서 유지(stable sort).

    [현재 미사용] 후보 10개에 동시 요청해 매칭되는 표를 고르는 방식이라
    순위 조정이 불필요. 보존만 해 둔다(필요 시 _search_one_claim 에서 재연결).
    """
    def _score(h: SearchHit) -> int:
        if h.stat_nm == "시군구통계":
            return 2
        if h.tbl_id.startswith("DT_2"):
            return 1
        return 0
    return sorted(hits, key=_score)


async def _search_one_claim(claim: Claim) -> ClaimAnalysis:
    """claim 1건 → 통합검색 → ClaimAnalysis (후보 풀 포함)."""
    keyword = _preprocess_subject(claim.subject or "")
    t0 = time.perf_counter()
    try:
        hits: list[SearchHit] = await asyncio.to_thread(
            search_tables, keyword, top_n=TOP_N
        )
    except (KosisError, ValueError) as exc:
        return _analysis(
            claim.claim_id,
            keyword,
            hits=[],
            success=0,
            error_msg=str(exc),
            duration_ms=_ms_since(t0),
        )
    return _analysis(
        claim.claim_id,
        keyword,
        hits=hits,
        success=1,
        error_msg=None,
        duration_ms=_ms_since(t0),
    )


def _analysis(
    claim_id: str,
    keyword: str,
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
            params=_params_log(keyword),
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


def _params_log(keyword: str) -> str:
    """검색 호출 파라미터를 로그용 JSON 문자열로. apiKey 는 절대 포함하지 않는다."""
    return json.dumps(
        {
            "method": "getList",
            "searchNm": keyword,
            "startCount": "1",
            "resultCount": str(TOP_N),
            "sort": "RANK",
            "format": "json",
        },
        ensure_ascii=False,
    )


def _ms_since(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
