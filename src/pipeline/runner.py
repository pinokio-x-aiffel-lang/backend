"""Pipeline — 단계 조립·실행, 이벤트 스트리밍.

단계 구현은 src/modules/ 에 단계당 1파일·1함수로 있고, 여기서 import 해 조립한다.
  - 각 함수 시그니처: (master_schema: MasterSchema) -> None (제자리 변경, 반환 없음)
  - 실패 시 raise → runner try/except 가 StepEvent(error) 로 변환·중단

Pipeline.run():
  - MasterSchema 하나를 만들어 단계들이 차례로 채운다 (직접 흐름)
  - 각 단계 시작/완료/오류를 StepEvent 로 yield
  - 전 단계 완료 후 ResultEvent yield
  - HTTP / SSE / Queue 등 전송 방식은 모름 → 호출자(verify_service)의 몫

HITL(create_hitl_task / save_hitl_feedback)은 선형 흐름 밖이라 run() 단계에 없다.
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
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.pipeline.events import PipelineEvent, ResultEvent, StepEvent
from src.schemas.runtime import MasterSchema


# ── Pipeline ─────────────────────────────────────────────────────────────────

class Pipeline:
    async def run(self, content: str) -> AsyncGenerator[PipelineEvent, None]:
        master_schema = MasterSchema(content=content)

        async for ev in self._step(1, "기사 내용 확인",               load_article,               master_schema): yield ev
        async for ev in self._step(2, "클레임 추출",                  extract_statistical_claims, master_schema): yield ev
        async for ev in self._step(3, "한국어 수사 산술로 변환",        normalize_claim,            master_schema): yield ev
        async for ev in self._step(4, "KOSIS 통계표 찾기",            retrieve_kosis_candidates,  master_schema): yield ev
        async for ev in self._step(5, "KOSIS 조회",                  fetch_kosis_data,           master_schema): yield ev
        async for ev in self._step(6, "통계 수치 비교 판단",           calculate_metric,           master_schema): yield ev
        async for ev in self._step(7, "통계수치와 문장의 정합성 판단",   check_alignment,            master_schema): yield ev
        async for ev in self._step(8, "종합 분석·검증 결과 생성",       decide_verdict,             master_schema): yield ev
        async for ev in self._step(9, "설명 생성",                   generate_explanation,       master_schema): yield ev

        yield ResultEvent(master_schema=master_schema)

    async def _step(self, step, name, fn, master_schema) -> AsyncGenerator[PipelineEvent, None]:
        t0 = time.monotonic()
        yield StepEvent(step=step, name=name, status="running")
        await asyncio.sleep(0.3)  # TEMP(ngrok SSE 테스트): 더미가 즉시 끝나 이벤트가 한 버스트로 몰리는 것 방지. 검증 후 제거.

        try:
            await fn(master_schema)
        except Exception as e:
            yield StepEvent(
                step=step, name=name, status="error",
                duration_ms=int((time.monotonic() - t0) * 1000),
                error=str(e),
            )
            raise
        
        # 멈췄다 재개하며 여러 값을 시간차로 내보내기 위해
        yield StepEvent(
            step=step, name=name, status="done",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
