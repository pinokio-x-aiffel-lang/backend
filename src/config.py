"""루트 검증 서버(main:app) 중앙 설정.

환경변수 이름은 필드명과 동일(대문자). 예: GOOGLE_CLIENT_ID=xxx
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # ── DB ──────────────────────────────────────────────────────────────────
    database_url: str = "postgresql://fnd:fnd@db:5432/fnd"

    # ── Google OAuth 2.0 ────────────────────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""

    # ── JWT ─────────────────────────────────────────────────────────────────
    jwt_secret_key: str = "change-me-in-production"
    jwt_expire_days: int = 7

    # ── 서비스 URL ───────────────────────────────────────────────────────────
    # 백엔드 기준 콜백 URL 생성에 사용. 운영 시 실제 도메인으로 설정 필요.
    backend_base_url: str = "http://localhost:8000"
    # 로그인 성공 후 리다이렉트할 프론트엔드 URL.
    frontend_base_url: str = "http://localhost:5174"

    # ── CORS 추가 허용 origin (쉼표 구분) ────────────────────────────────────
    frontend_origins: str = ""

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.backend_base_url}/auth/google/callback"

    @property
    def database_url_async(self) -> str:
        """SQLAlchemy 비동기(psycopg3) 드라이버 URL로 변환."""
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    @property
    def cookie_secure(self) -> bool:
        """HTTPS 환경이면 OAuth state 쿠키에 Secure 플래그 적용."""
        return self.backend_base_url.startswith("https://")


def load_settings() -> Settings:
    return Settings()
