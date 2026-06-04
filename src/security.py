"""레이트리밋 + IP 차단(블랙리스트) — `POST /verify` 보호.

규칙(값은 src/config.py, 환경변수로 override):
- 60초 슬라이딩 윈도우에서 `rate_max_hits`(기본 15)를 초과하면(=16번째) '적발'.
- 1·2차 적발 = `block_first_seconds`(1시간), 3차+ = `block_repeat_seconds`(24시간) 차단.
- 마지막 적발 후 `offense_decay_seconds`(24시간) 무사고면 누적 적발 카운트를 0으로
  리셋한다(영구 누적 방지 → 최대 벌칙은 24시간).
- 상태는 in-memory(단일 워커 전제). 재시작/재배포 시 초기화되고, 다중 인스턴스에는
  공유되지 않는다(그 경우 Redis 등 외부 저장소 필요).
- IP는 Cloudflare/프록시 뒤이므로 CF-Connecting-IP → X-Forwarded-For → 소켓 순으로 식별.

동시성: 의존성 `rate_limit`은 async 라 이벤트 루프에서 실행되고, `check()`는 await 없이
동기적으로 끝나므로 단일 워커에서는 상태 dict 접근이 원자적이다(스레드풀 미사용).
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from fastapi import Request
from fastapi.responses import JSONResponse

from src.config import Settings, load_settings


def client_ip(request: Request) -> str:
    """프록시 뒤 실제 클라이언트 IP. (CF-Connecting-IP → X-Forwarded-For → 소켓)"""
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimited(Exception):
    """레이트리밋 차단 신호. main.py 의 예외 핸들러가 429 로 변환한다."""

    def __init__(self, retry_after: float):
        self.retry_after = max(1, int(retry_after))
        super().__init__(f"rate limited; retry after {self.retry_after}s")


@dataclass
class _IpState:
    hits: deque[float] = field(default_factory=deque)  # 최근 요청 timestamp(윈도우 내)
    offenses: int = 0                                   # 누적 적발 횟수
    last_offense: float = 0.0                           # 마지막 적발 시각(decay 기준)
    blocked_until: float = 0.0                          # 이 시각 전까지 차단


class RateLimiter:
    """IP별 슬라이딩 윈도우 카운트 + 에스컬레이션 차단."""

    def __init__(self, settings: Settings):
        self._s = settings
        self._states: dict[str, _IpState] = {}
        self._last_sweep = 0.0

    def check(self, ip: str, now: float | None = None) -> None:
        """허용이면 그냥 반환, 차단이면 RateLimited 발생."""
        s = self._s
        now = time.monotonic() if now is None else now
        st = self._states.get(ip)
        if st is None:
            st = self._states[ip] = _IpState()

        # 0) 누적 적발 decay: 마지막 적발 후 충분히 지나면 리셋(영구 누적 방지)
        if st.offenses and now - st.last_offense > s.offense_decay_seconds:
            st.offenses = 0

        # 1) 이미 차단 중이면 즉시 거부(요청 기록/적발 카운트 안 함)
        if now < st.blocked_until:
            self._maybe_sweep(now)
            raise RateLimited(st.blocked_until - now)

        # 2) 요청 기록 + 윈도우 밖(오래된) 항목 제거
        st.hits.append(now)
        cutoff = now - s.rate_window_seconds
        while st.hits and st.hits[0] <= cutoff:
            st.hits.popleft()

        # 3) 허용 횟수 초과 → 적발 + 차단
        if len(st.hits) > s.rate_max_hits:
            st.offenses += 1
            st.last_offense = now
            dur = (
                s.block_repeat_seconds
                if st.offenses >= s.repeat_threshold
                else s.block_first_seconds
            )
            st.blocked_until = now + dur
            st.hits.clear()
            self._maybe_sweep(now)
            raise RateLimited(dur)

        self._maybe_sweep(now)

    def _maybe_sweep(self, now: float) -> None:
        """만료된 IP 항목을 주기적으로 정리(메모리 누수 방지)."""
        if now - self._last_sweep < self._s.ratelimit_sweep_seconds:
            return
        self._last_sweep = now
        cutoff = now - self._s.rate_window_seconds
        dead = [
            ip
            for ip, st in self._states.items()
            if now >= st.blocked_until
            and st.offenses == 0
            and (not st.hits or st.hits[-1] <= cutoff)
        ]
        for ip in dead:
            del self._states[ip]


# 단일 인스턴스(모듈 로드 시 1회 생성). 설정은 환경변수에서.
limiter = RateLimiter(load_settings())


async def rate_limit(request: Request) -> None:
    """`POST /verify` 의존성. 차단 시 RateLimited 발생."""
    limiter.check(client_ip(request))


def _fmt_duration(secs: int) -> str:
    if secs >= 3600:
        return f"약 {secs // 3600}시간"
    return f"약 {max(1, secs // 60)}분"


async def ratelimited_handler(request: Request, exc: RateLimited) -> JSONResponse:
    """RateLimited → 429 JSON({"message": ...}) + Retry-After. (프론트 에러 UI 호환)"""
    return JSONResponse(
        status_code=429,
        content={
            "message": f"요청이 너무 많습니다. {_fmt_duration(exc.retry_after)} 후 다시 시도해 주세요."
        },
        headers={"Retry-After": str(exc.retry_after)},
    )
