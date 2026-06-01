"""Pipeline — 단계 조립·실행, 이벤트 스트리밍.

단계 구현은 src/modules/ 에 단계당 1파일·1함수로 있고, 여기서 import 해 조립한다.
  - 각 함수 시그니처: (record: MasterSchema) -> None (제자리 변경, 반환 없음)
  - 실패 시 raise → runner try/except 가 StepEvent(error) 로 변환·중단

Pipeline.run():
  - MasterSchema 하나를 만들어 단계들이 차례로 채운다 (직접 흐름)
  - 각 단계 시작/완료/오류를 StepEvent 로 yield
  - 전 단계 완료 후 ResultEvent yield
  - HTTP / SSE / Queue 등 전송 방식은 모름 → 호출자(verify_service)의 몫

HITL(create_hitl_task / save_hitl_feedback)은 선형 흐름 밖이라 _STEPS 에 없다.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator

from src.modules.calculate_metric import calculate_metric
from src.modules.check_alignment import check_alignment
from src.modules.decide_verdict import decide_verdict
from src.modules.extract_statistical_claims import extract_statistical_claims
from src.modules.fetch_kosis_data import fetch_kosis_data
from src.modules.generate_explanation import generate_explanation
from src.modules.load_article import load_article
from src.modules.normalize_claim import normalize_claim
from src.modules.rank_evidence import rank_evidence
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.pipeline.events import PipelineEvent, ResultEvent, StepEvent
from src.schemas.runtime import MasterSchema


# ── 단계 목록 (순서 고정) ─────────────────────────────────────────────────────

_STEPS = [
    ("기사 내용 확인",                load_article),
    ("클레임 추출",                   extract_statistical_claims),
    ("한국어 수사 산술로 변환",        normalize_claim),
    ("KOSIS 통계표 찾기",             retrieve_kosis_candidates),
    ("KOSIS 조회",                    fetch_kosis_data),
    ("증거 랭킹",                     rank_evidence),
    ("통계 수치 비교 판단",            calculate_metric),
    ("통계수치와 문장의 정합성 판단",  check_alignment),
    ("종합 분석·검증 결과 생성",       decide_verdict),
    ("설명 생성",                     generate_explanation),
]


# ── Pipeline ─────────────────────────────────────────────────────────────────

class Pipeline:
    async def run(self, content: str) -> AsyncGenerator[PipelineEvent, None]:
        record = MasterSchema(content=content)

        for i, (name, fn) in enumerate(_STEPS, 1):
            t0 = time.monotonic()
            yield StepEvent(step=i, name=name, status="running")
            await asyncio.sleep(1.5)  # TEMP(ngrok SSE 테스트): 더미가 즉시 끝나 이벤트가 한 버스트로 몰리는 것 방지. 검증 후 제거.

            try:
                await fn(record)
            except Exception as e:
                yield StepEvent(
                    step=i, name=name, status="error",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    error=str(e),
                )
                raise

            yield StepEvent(
                step=i, name=name, status="done",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        yield ResultEvent(record=record)
