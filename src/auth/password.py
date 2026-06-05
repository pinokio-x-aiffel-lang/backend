"""bcrypt 비밀번호 해싱.

passlib 대신 bcrypt 라이브러리를 직접 사용한다
(passlib 1.7.4 는 bcrypt 5.x 와 비호환 — backend 탐지에서 깨짐).
주의: bcrypt 는 비밀번호 72바이트까지만 사용한다(초과분은 무시).
"""
from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
