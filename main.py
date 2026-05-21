from fastapi import FastAPI
from src.schemas.verify import VerifyRequest, VerifyResponse
from src.services.verify_service import verify_article
from fastapi.responses import StreamingResponse
import json, asyncio, uuid

jobs: dict[str, asyncio.Queue] = {}  # job_id → 이벤트 큐

app = FastAPI(
    title="Fake News Verification API",
    version="0.1.0",
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite 개발 서버 주소
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/verify", response_model=VerifyResponse)
async def verify(request: VerifyRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs[job_id] = asyncio.Queue()
    background_tasks.add_task(run_pipeline, job_id, req.content)
    return {"job_id": job_id}
    # return await verify_article(request)

async def run_pipeline(job_id: str, content: str):
    q = jobs[job_id]
    # 각 단계마다
    await q.put({"event": "step", "data": {...}})
    # 완료 시
    await q.put({"event": "result", "data": verify_response})
    await q.put(None)  # 종료 신호

@app.get("/verify/stream")
  async def stream(job_id: str):
      async def generator():
          q = jobs[job_id]
          while True:
              item = await q.get()
              if item is None:
                  del jobs[job_id]
                  break
              yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"
      return EventSourceResponse(generator())