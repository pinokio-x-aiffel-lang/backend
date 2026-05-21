"""환경변수 로드.

HCX 시크릿(`CLOVASTUDIO_API_KEY`)은 Infisical CLI 가 프로세스에 주입한다.
즉 서버는 `uv run x uvicorn ...`(= `infisical run -- uv run ...`) 로 기동해야
하며, 코드는 주입된 환경변수만 읽는다. Python Infisical SDK 는 사용하지 않는다.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """서버 설정. 값은 환경변수(또는 Infisical 주입)에서만 온다."""

    # env_file 을 쓰지 않는다. HCX 키를 .env 에서 읽으면 Infisical 전용
    # 정책(API_rule §4.1)과 fail-fast 가 무력화된다. 값은 오직 Infisical
    # CLI 가 주입한 프로세스 환경변수에서만 온다.
    model_config = SettingsConfigDict(extra="ignore")

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    log_dir: str = "./logs"

    # HCX 키. Infisical CLI 가 이 이름으로 주입한다(로컬 .env 와 동일 이름).
    # 기존 llm/client.py 는 HCX_API_KEY 를 읽지만 수정 금지이므로,
    # 여기서 읽어 ChatClient(api_key=...) 로 명시 전달해 이름 차이를 흡수한다.
    clovastudio_api_key: str | None = None

    default_timeout_seconds: float = 60.0


def load_settings() -> Settings:
    """설정 1회 로드."""
    return Settings()
