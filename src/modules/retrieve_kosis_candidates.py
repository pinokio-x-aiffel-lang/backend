from __future__ import annotations

from src.schemas.runtime import ClaimAnalysis, KosisQuery, KosisSearch, MasterSchema


class RetrieveKosisCandidatesError(Exception):
    """KOSIS 후보 통계표 검색 실패."""


async def retrieve_kosis_candidates(record: MasterSchema) -> None:
    """
    [4] Retrieve KOSIS Candidates

    Input:
        record.claims         # subject / unit / period 등

    Output:
        record.analysis       # claim별 ClaimAnalysis 초기화 (kosis_search 채움)

    Responsibility:
        claim별 subject+unit 로 KOSIS 통합검색(statisticsSearch.do)을 호출해
        후보 통계표를 찾고 가장 적합한 테이블을 선정, record.analysis 를 초기화한다.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    # TODO: 실제 구현 — KOSIS statisticsSearch.do 호출. 현재는 happy-path 더미.
    #       kosis_query 는 placeholder 로 두고 [5] fetch_kosis_data 에서 채운다.
    record.analysis = [
        ClaimAnalysis(
            claim_id=claim.claim_id,
            kosis_search=KosisSearch(
                api="statisticsSearch.do",
                query=claim.subject,
                params="(더미)",
                hits=1,
                selected_tbl_id="DT_DUMMY",
                selected_tbl_name="(더미) 인구동향조사",
                success=1,
                duration_ms=0,
            ),
            kosis_query=KosisQuery(
                api="statisticsData.do",
                tbl_id="DT_DUMMY",
                params="",
                rows_returned=0,
                success=0,
                duration_ms=0,
            ),
        )
        for claim in record.claims
    ]
