from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from src.config import load_settings

_s = load_settings()
_ALGORITHM = "HS256"


def create_access_token(user_id: str, name: str | None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=_s.jwt_expire_days)
    return jwt.encode(
        {"sub": user_id, "name": name, "exp": expire},
        _s.jwt_secret_key,
        algorithm=_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    """유효한 토큰이면 payload dict 반환, 아니면 빈 dict."""
    try:
        return jwt.decode(token, _s.jwt_secret_key, algorithms=[_ALGORITHM])
    except JWTError:
        return {}
