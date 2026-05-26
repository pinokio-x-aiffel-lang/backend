from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from src.schemas.verify import VerifyRequest
from src.services.verify_service import run_pipeline_with_queue
import json, asyncio, uuid

jobs: dict[str, tuple[asyncio.Queue, asyncio.Task]] = {}

app = FastAPI(
    title="Fake News Verification API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/verify")
async def verify(request: VerifyRequest):
    job_id = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(run_pipeline_with_queue(q, request.content))
    jobs[job_id] = (q, task)
    return {"job_id": job_id}


@app.get("/verify/stream")
async def stream(job_id: str):
    if job_id not in jobs:
        async def not_found():
            yield {"event": "error", "data": json.dumps({"message": "job not found"}, ensure_ascii=False)}
        return EventSourceResponse(not_found())

    q, task = jobs[job_id]

    async def generator():
        try:
            while True:
                item = await q.get()
                if item is None:
                    break
                yield {"event": item["event"], "data": json.dumps(item["data"], ensure_ascii=False)}
        finally:
            task.cancel()
            jobs.pop(job_id, None)

    return EventSourceResponse(generator())
