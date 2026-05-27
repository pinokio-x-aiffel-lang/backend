#!/usr/bin/env bash
# 컨테이너 진입점.
# INFISICAL_TOKEN 이 있으면 `infisical run` 으로 시크릿을 주입한 뒤 uvicorn 기동,
# 없으면(로컬/시크릿 불필요 테스트) Infisical 없이 기동한다.
set -euo pipefail

APP_MODULE="${APP_MODULE:-main:app}"
HOST="${APP_HOST:-0.0.0.0}"
PORT="${APP_PORT:-8000}"

if [ -n "${INFISICAL_TOKEN:-}" ]; then
  echo "[entrypoint] Infisical 시크릿 주입 후 기동: ${APP_MODULE} @ ${HOST}:${PORT}"
  exec infisical run --token="${INFISICAL_TOKEN}" --silent -- \
    uv run --no-sync uvicorn "${APP_MODULE}" --host "${HOST}" --port "${PORT}"
else
  echo "[entrypoint] 경고: INFISICAL_TOKEN 미설정 — Infisical 시크릿 주입 없이 기동합니다." >&2
  exec uv run --no-sync uvicorn "${APP_MODULE}" --host "${HOST}" --port "${PORT}"
fi
