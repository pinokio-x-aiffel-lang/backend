from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from src.config import load_settings

_s = load_settings()
_ALGORITHM = "HS256"


def create_access_token(user_id: str, name: str | None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=_s.jwt_expire_days)
    return jwt.encode(
        # jti: 토큰 고유 ID — 로그아웃 시 denylist 등록/조회 키로 쓴다.
        {"sub": user_id, "name": name, "jti": uuid.uuid4().hex, "exp": expire},
        _s.jwt_secret_key,
        algorithm=_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    """유효한 토큰이면 payload dict 반환, 아니면 빈 dict."""
    try:
        return jwt.decode(token, _s.jwt_secret_key, algorithms=[_ALGORITHM])
    except JWTError:
        return {}
