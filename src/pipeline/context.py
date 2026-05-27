"""파이프라인 단계 간 흐르는 데이터 컨테이너."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.schemas.claim import Article, Claim, ClaimAnalysis, Verifications


@dataclass
class PipelineContext:
    """파이프라인 실행 중 단계들이 공유하는 상태.

    각 단계는 자신의 산출물을 해당 필드에 채워 넣고 ctx를 반환한다.
    필드는 순서대로 채워진다:
      content → article → claims → analysis → verifications
    """

    content: str                          # 입력: 기사 본문 또는 URL

    article: Article | None = None        # s01 이후
    claims: list[Claim] = field(default_factory=list)          # s02 이후
    analysis: list[ClaimAnalysis] = field(default_factory=list)  # s03~s04 이후
    verifications: Verifications | None = None                 # s10 이후
