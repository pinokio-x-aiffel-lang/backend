#!/usr/bin/env bash
# Infisical 이 CLOVASTUDIO_API_KEY 를 주입하도록 `uv run x` 경유로 기동한다.
# (x = scripts/run.py = `infisical run -- uv run`)
# 프로젝트 루트에서 실행해야 한다(src 가 import 가능하도록).
set -euo pipefail

cd "$(dirname "$0")/../.."   # → 프로젝트 루트

HOST="${APP_HOST:-0.0.0.0}"
PORT="${APP_PORT:-8000}"

exec uv run x uvicorn src.api.main:app --host "$HOST" --port "$PORT"
