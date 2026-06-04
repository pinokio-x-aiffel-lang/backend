"""비동기 DB 엔진 + 세션 팩토리.

SQLAlchemy async + psycopg3 드라이버 사용.
DATABASE_URL 환경변수: postgresql://... → postgresql+psycopg://...
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.auth.models import Base
from src.config import load_settings

_s = load_settings()

engine = create_async_engine(_s.database_url_async, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """앱 기동 시 users 테이블 생성 (없을 경우에만)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
