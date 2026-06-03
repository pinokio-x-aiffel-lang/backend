"""FastAPI 앱 — 라우터 등록, 글로벌 예외 핸들러, 기동 시 fail-fast.

기동:  uv run x uvicorn src.api.chat_app:app --host 0.0.0.0 --port 8000
      (= infisical run -- uv run uvicorn ... → CLOVASTUDIO_API_KEY 주입)
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.api.config import load_settings
from src.api.logging_utils import JsonlLogger
from src.api.providers.registry import build_registry
from src.api.routers import chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    # HCX 키가 주입되지 않았으면 여기서 즉시 실패 → 서버가 뜨지 않음.
    app.state.registry = build_registry(settings)
    app.state.logger = JsonlLogger(settings.log_dir)
    app.state.settings = settings
    yield


app = FastAPI(title="LLM Chat API", version="0.1.0", lifespan=lifespan)
app.include_router(chat.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
    )


@app.exception_handler(HTTPException)
async def http_exc_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        return _error(exc.status_code, detail["code"], detail.get("message", ""))
    return _error(exc.status_code, "http_error", str(detail))


@app.exception_handler(RequestValidationError)
async def validation_exc_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    return _error(422, "validation_error", str(exc.errors()))


@app.exception_handler(Exception)
async def unhandled_exc_handler(_: Request, exc: Exception) -> JSONResponse:
    return _error(500, "internal_error", str(exc))
