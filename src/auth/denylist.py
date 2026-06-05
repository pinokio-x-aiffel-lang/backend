"""로그아웃된 토큰의 in-memory denylist (jti 기준).

⚠️ 프로세스 메모리(앱과 같은 프로세스)에만 존재한다. 따라서:
   - 앱 재시작/재배포 시 사라진다(폐기가 풀림 — 로그아웃했던 토큰이 다시 유효).
   - 여러 인스턴스 간 공유되지 않는다.
   영속·공유가 필요하면 Redis/Postgres 로 이 모듈만 교체하면 된다(인터페이스 동일).
"""
from __future__ import annotations

import time

# jti -> 토큰 만료(epoch 초). 만료가 지난 항목은 정리 대상(메모리 누수 방지).
_revoked: dict[str, float] = {}


def revoke(jti: str, exp: float) -> None:
    """해당 jti 를 만료시각(exp)까지 denylist 에 등록."""
    _prune()
    _revoked[jti] = exp


def is_revoked(jti: str) -> bool:
    """denylist 에 살아있는(미만료) 항목으로 존재하면 True."""
    exp = _revoked.get(jti)
    if exp is None:
        return False
    if exp < time.time():
        _revoked.pop(jti, None)  # 만료된 항목은 즉시 제거
        return False
    return True


def _prune() -> None:
    """만료된 항목 일괄 정리."""
    now = time.time()
    for jti in [j for j, e in _revoked.items() if e < now]:
        _revoked.pop(jti, None)
