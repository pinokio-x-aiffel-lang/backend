"""verify_service — Queue ↔ Pipeline 어댑터.

FastAPI(main.py)가 생성한 asyncio.Queue를 받아
Pipeline 이벤트를 SSE 포맷({event, data})으로 변환해 넣는다.
비즈니스 로직은 없음 — 모두 Pipeline의 몫.
"""
from __future__ import annotations

import asyncio

from src.api.verify import to_verify_response
from src.pipeline import Pipeline, ResultEvent, StepEvent


async def run_pipeline_with_queue(q: asyncio.Queue, content: str) -> None:
    try:
        pipeline = Pipeline()
        async for event in pipeline.run(content):
            if isinstance(event, StepEvent):
                await q.put({
                    "event": "step",
                    "data": {
                        "step": event.step,
                        "name": event.name,
                        "status": event.status,
                        "duration_ms": event.duration_ms,
                        "error": event.error,
                    },
                })
            elif isinstance(event, ResultEvent):
                # 경계 매핑: MasterSchema → VerifyResponse(프론트 계약)
                payload = to_verify_response(event.master_schema)
                await q.put({"event": "result", "data": payload.model_dump()})
    except Exception as e:
        await q.put({"event": "error", "data": {"message": str(e)}})
    finally:
        await q.put(None)
