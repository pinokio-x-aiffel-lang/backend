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
from src.modules.rank_evidence import rank_evidence
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.pipeline.events import PipelineEvent, ResultEvent, StepEvent
from src.schemas.runtime import MasterSchema


# ── Pipeline ─────────────────────────────────────────────────────────────────

class Pipeline:
    async def run(self, content: str, on_step=None) -> AsyncGenerator[PipelineEvent, None]:
        master_schema = MasterSchema(content=content)

        async for ev in self._step(1, "기사 내용 확인", load_article, master_schema, on_step): yield ev
        async for ev in self._step(2, "클레임 추출", extract_statistical_claims, master_schema, on_step): yield ev
        async for ev in self._step(3, "한국어 수사 산술로 변환", normalize_claim, master_schema, on_step): yield ev
        async for ev in self._step(4, "KOSIS 통계표 n개 찾기", retrieve_kosis_candidates, master_schema, on_step): yield ev
        async for ev in self._step(5, "KOSIS 셀 값 조회", fetch_kosis_data, master_schema, on_step): yield ev
        async for ev in self._step(6, "증거 랭킹", rank_evidence, master_schema, on_step): yield ev
        async for ev in self._step(7, "통계 수치 비교 판단", calculate_metric, master_schema, on_step): yield ev
        async for ev in self._step(8, "통계수치와 문장의 정합성 판단", check_alignment, master_schema, on_step): yield ev
        async for ev in self._step(9, "종합 분석·검증 결과 생성", decide_verdict, master_schema, on_step): yield ev
        async for ev in self._step(10, "설명 생성", generate_explanation, master_schema, on_step): yield ev

        yield ResultEvent(master_schema=master_schema)

    async def _step(self, step, name, fn, master_schema, on_step=None) -> AsyncGenerator[PipelineEvent, None]:
        t0 = time.monotonic()
        yield StepEvent(step=step, name=name, status="running")
        await asyncio.sleep(0.01)  # TEMP(ngrok SSE 테스트): 더미가 즉시 끝나 이벤트가 한 버스트로 몰리는 것 방지. 검증 후 제거.

        try:
            await fn(master_schema)
        except Exception as e:
            yield StepEvent(
                step=step, name=name, status="error",
                duration_ms=int((time.monotonic() - t0) * 1000),
                error=str(e),
            )
            raise
        
        duration_ms = int((time.monotonic() - t0) * 1000)
        if on_step is not None:
            on_step(step, name, master_schema)

        # 멈췄다 재개하며 여러 값을 시간차로 내보내기 위해
        yield StepEvent(
            step=step, name=name, status="done",
            duration_ms=duration_ms,
        )



if __name__ == "__main__":
    import sys

    from src.pipeline.result_md import DEFAULT_RESULT_PATH, make_result_recorder

    async def _main() -> None:
        no_content = "기사가 없습니다."
        sample_content = "통계청에 따르면 지난달 한국 근로자의 주당 평균 근로시간은 38.8시간이다. 맥킨지는 노동시장 참여율을 높이는 것도 방법이라고 했다. 이 중 고령 인구가 노동시장에 남는 비율, 즉 ‘근로 수명’을 높이는 것도 고려해야 한다는 것이다. 일본의 경우 65세 이상 노동시장 참여율(26%)이 프랑스(4%) 등을 앞서고 있으며, 이는 일본의 1997년 이후 연평균 노동생산성 증가율(1.1%)이 서유럽(0.8%)을 앞설 수 있던 요인이 됐다고 했다. 하지만 맥킨지는 일본 방식도 한계는 있다고 봤다. 일본의 경우 25~64세는 주당 평균 30시간을 일하지만, 65세 이상은 7시간 일하는 것으로 집계돼 결국 고령화에 따른 노동시간 감소는 피할 수 없기 때문이다."

        content = sys.argv[1] if len(sys.argv) > 1 else sample_content
        recorder = make_result_recorder(content)  # tests/result.md 초기화 + 단계별 기록 콜백

        async for ev in Pipeline().run(content, on_step=recorder):
            print(ev)
        print(f"[result.md 저장] {DEFAULT_RESULT_PATH}")

    asyncio.run(_main())