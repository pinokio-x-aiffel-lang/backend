"""파이프라인이 외부로 emit하는 이벤트 타입."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.schemas.runtime import MasterSchema


@dataclass
class StepEvent:
    """단계 시작/완료/오류 알림."""

    step: int
    name: str
    status: Literal["running", "done", "error"]
    duration_ms: int | None = None
    error: str | None = None


@dataclass
class ResultEvent:
    """파이프라인 최종 결과 — 채워진 MasterSchema."""

    record: MasterSchema


# Pipeline.run()이 yield하는 타입
PipelineEvent = StepEvent | ResultEvent
