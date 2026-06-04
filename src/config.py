"""검증 서버(루트 `main:app`) 중앙 설정.

값은 코드 기본값 + 환경변수 override(pydantic-settings). 시크릿은 넣지 않는다.
(예: `RATE_MAX_HITS=20` 환경변수가 `rate_max_hits` 기본값을 덮는다.)
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """검증 서버 설정. 필드명(대문자)과 동일한 환경변수로 override 가능."""

    model_config = SettingsConfigDict(extra="ignore")

    # ── 레이트리밋 / IP 차단 (src/security.py) ──────────────────────────────
    rate_window_seconds: int = 60        # 슬라이딩 윈도우 길이(초)
    rate_max_hits: int = 6               # 윈도우당 허용 횟수 → 7번째부터 적발
    block_first_seconds: int = 3600      # 1·2차 적발 차단(1시간)
    block_repeat_seconds: int = 86400    # 3차+ 적발 차단(24시간)
    repeat_threshold: int = 3            # 누적 적발 이 값 이상이면 장기 차단
    offense_decay_seconds: int = 86400   # 마지막 적발 후 이 시간 무사고면 누적 0으로 리셋
    ratelimit_sweep_seconds: int = 600   # 만료 IP 항목 정리 주기(메모리 누수 방지)

    # ── DB ──────────────────────────────────────────────────────────────────
    database_url: str = "postgresql://fnd:fnd@db:5432/fnd"

    # ── JWT ─────────────────────────────────────────────────────────────────
    jwt_secret_key: str = "change-me-in-production"
    jwt_expire_days: int = 7

    @property
    def database_url_async(self) -> str:
        """SQLAlchemy 비동기(psycopg3) 드라이버 URL로 변환."""
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)


def load_settings() -> Settings:
    """설정 1회 로드."""
    return Settings()
