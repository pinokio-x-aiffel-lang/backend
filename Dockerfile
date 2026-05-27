# fake-news-detector — FastAPI(main:app) 배포 이미지
# 기동: Infisical CLI 가 LLM/HCX 시크릿을 프로세스에 주입한 뒤 uvicorn 을 띄운다.
#   (infisical run -- uv run uvicorn main:app)  ← docker/entrypoint.sh 참고
#
# 베이스: uv + CPython 3.11 (Debian bookworm) → apt 로 Infisical CLI 설치 가능.
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON=3.11 \
    PYTHONUNBUFFERED=1

# 시스템 의존성 + Infisical CLI
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates bash \
 && curl -1sLf 'https://artifacts-cli.infisical.com/setup.deb.sh' | bash \
 && apt-get update \
 && apt-get install -y --no-install-recommends infisical \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) 의존성 레이어 (pyproject/lock 이 바뀔 때만 재빌드 → 캐시 효율)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) 애플리케이션 소스
COPY . .
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000

RUN chmod +x /app/docker/entrypoint.sh
ENTRYPOINT ["/app/docker/entrypoint.sh"]
