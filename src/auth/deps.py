"""FastAPI 의존성: 현재 인증된 사용자 반환.

사용법:
    @app.post("/verify", dependencies=[Depends(get_current_user)])
    또는
    async def endpoint(user: dict = Depends(get_current_user)):
        ...
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.denylist import is_revoked
from src.auth.jwt_handler import decode_access_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Bearer 토큰 검증 후 payload 반환. 미인증 시 401."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 인증 토큰입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if is_revoked(payload.get("jti", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그아웃된 토큰입니다. 다시 로그인하세요.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict | None:
    """get_current_user 의 비강제 버전 — 토큰이 유효하면 payload, 없거나 무효면 None.

    인증을 강제하지 않고 '로그인 여부'만 알아야 하는 곳(예: 티어 레이트리밋)에서 쓴다.
    """
    if not credentials:
        return None
    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        return None
    if is_revoked(payload.get("jti", "")):
        return None
    return payload
