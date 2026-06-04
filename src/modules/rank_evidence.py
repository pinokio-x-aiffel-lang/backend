from __future__ import annotations

from src.schemas.runtime import MasterSchema


class RankEvidenceError(Exception):
    """증거 랭킹 실패."""


async def rank_evidence(record: MasterSchema) -> None:
    """
    [6] Rank Evidence

    Input:
        record.analysis       # [5]에서 수집된 Evidence 후보

    Output:
        claim별 비교에 쓸 대표 Evidence 선정 결과

    Responsibility:
        claim 별로 수집된 Evidence 후보를 적합도(기간·집계·단위 일치 등)로
        정렬해 비교에 쓸 대표 증거를 선정한다.
        실패 시 raise → runner 가 StepEvent(error) 로 처리.
    """
    # TODO: 실제 구현 — Evidence 후보 랭킹·선정.
    #       현재 스키마상 중간 상태 저장처가 없어 happy-path 에선 no-op.
    pass
