from contextlib import asynccontextmanager
import json
import asyncio
import uuid
import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from src.api.verify import VerifyRequest
from src.security import RateLimited, rate_limit, ratelimited_handler
from src.services.verify_service import run_pipeline_with_queue
from src.auth.database import init_db
from src.auth.router import router as auth_router
from src.auth.deps import get_current_user

jobs: dict[str, tuple[asyncio.Queue, asyncio.Task]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Fake News Verification API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 허용 origin: 로컬 개발 + 운영 프론트엔드 + FRONTEND_ORIGINS(쉼표 구분) 환경변수
_default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "https://pinokiox-frontend.onrender.com",
]
_env_origins = [o.strip() for o in os.environ.get("FRONTEND_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[*_default_origins, *_env_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 레이트리밋 차단(RateLimited) → 429 JSON 응답으로 변환
app.add_exception_handler(RateLimited, ratelimited_handler)
app.include_router(auth_router)


@app.get("/")
async def root():
    return {
        "service": "Fake News Verification API",
        "version": "0.1.0",
        "message": "환영합니다 — 가짜뉴스 검증 API 입니다.",
        "endpoints": {
            "health": "GET /health",
            "verify": "POST /verify  (로그인 필요)",
            "stream": "GET /verify/stream?job_id=...",
            "register": "POST /auth/register",
            "login": "POST /auth/login",
            "me": "GET /auth/me",
            "docs": "GET /docs",
        },
    }


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/verify", dependencies=[Depends(rate_limit), Depends(get_current_user)])
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
