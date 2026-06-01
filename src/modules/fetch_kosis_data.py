from __future__ import annotations

from src.schemas.runtime import KosisQuery, MasterSchema


class FetchKosisDataError(Exception):
    """KOSIS 통계자료 조회 실패."""


async def fetch_kosis_data(record: MasterSchema) -> None:
    """
    [5] Fetch KOSIS Data

    Input:
        record.analysis       # [4]에서 선정된 통계표 (selected_tbl_id)

    Output:
        record.analysis[*].kosis_query   # 조회 로그
        + 조회된 공식 수치 (Evidence 후보)

    Responsibility:
        선정 테이블에서 claim 의 period/population 에 맞는 행을 조회한다
        (statisticsData.do). 조회 로그를 kosis_query 에 기록하고
        공식 수치를 Evidence 후보로 수집한다.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    # TODO: 실제 구현 — KOSIS statisticsData.do 조회 + Evidence 수집. 현재는 더미.
    for item in record.analysis:
        item.kosis_query = KosisQuery(
            api="statisticsData.do",
            tbl_id=item.kosis_search.selected_tbl_id or "DT_DUMMY",
            params="(더미)",
            rows_returned=1,
            success=1,
            duration_ms=0,
        )
