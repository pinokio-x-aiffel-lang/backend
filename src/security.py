"""레이트리밋 + IP 차단(블랙리스트).

두 의존성을 제공한다(둘 다 IP 기준, 값은 src/config.py·환경변수 override):
- `rate_limit` — 글로벌(예: GET /result). `rate_window_seconds`(60초) 윈도우에서
  `rate_max_hits`(6)를 초과하면 적발 → `block_first_seconds`(1시간), 누적
  `repeat_threshold`(3)회+면 `block_repeat_seconds`(24시간) 차단. 마지막 적발 후
  `offense_decay_seconds`(24시간) 무사고면 누적 0으로 리셋(최대 벌칙 24시간).
- `verify_rate_limit` — POST /verify 전용 티어:
  · 비로그인: `verify_rate_window_seconds`(1시간) 윈도우 `verify_rate_max_hits`(20)회,
    초과 시 위와 같은 에스컬레이션 차단.
  · admin(JWT `sub == admin_id`): `admin_rate_window_seconds`(1시간)
    `admin_rate_max_hits`(200)회까지 허용. 초과 시 가장 오래된 요청이 윈도우 밖으로
    빠질 때까지만 429 — 장기 차단/에스컬레이션 없음.

상태는 in-memory(단일 워커 전제). 재시작/재배포 시 초기화, 다중 인스턴스엔 비공유
(그 경우 Redis 등 필요). IP는 프록시 뒤이므로 CF-Connecting-IP → X-Forwarded-For → 소켓.
동시성: 의존성은 async, `check()`는 await 없이 동기 종료 → 단일 워커에서 상태 접근 원자적.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from src.auth.deps import get_current_user_optional
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


class SlidingWindowLimiter:
    """단순 키별 슬라이딩 윈도우 — 에스컬레이션/장기차단 없음.

    윈도우 내 max_hits 회까지 허용, 도달 시 가장 오래된 요청이 윈도우 밖으로 빠질
    때까지만 429(그만큼만 retry_after). admin 완화 한도에 쓴다.
    """

    def __init__(self, window_seconds: int, max_hits: int, sweep_seconds: int) -> None:
        self._window = window_seconds
        self._max = max_hits
        self._sweep_every = sweep_seconds
        self._hits: dict[str, deque[float]] = {}
        self._last_sweep = 0.0

    def check(self, key: str, now: float | None = None) -> None:
        """허용이면 그냥 반환, 한도 도달이면 RateLimited 발생."""
        now = time.monotonic() if now is None else now
        dq = self._hits.get(key)
        if dq is None:
            dq = self._hits[key] = deque()
        cutoff = now - self._window
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if len(dq) >= self._max:
            # 가장 오래된 요청이 윈도우를 벗어나면 한 칸 빈다 → 그때까지만 대기.
            raise RateLimited(dq[0] + self._window - now)
        dq.append(now)
        self._maybe_sweep(now)

    def _maybe_sweep(self, now: float) -> None:
        if now - self._last_sweep < self._sweep_every:
            return
        self._last_sweep = now
        cutoff = now - self._window
        dead = [k for k, dq in self._hits.items() if not dq or dq[-1] <= cutoff]
        for k in dead:
            del self._hits[k]


# ── 리미터 인스턴스(모듈 로드 시 1회). 설정은 환경변수에서. ────────────────────
_settings = load_settings()

# 글로벌(예: GET /result) — rate_window_seconds/rate_max_hits + 에스컬레이션.
limiter = RateLimiter(_settings)

# POST /verify 비로그인 — IP별 1시간 윈도우 10회 + 에스컬레이션.
_anon_verify_limiter = RateLimiter(
    _settings.model_copy(
        update={
            "rate_window_seconds": _settings.verify_rate_window_seconds,
            "rate_max_hits": _settings.verify_rate_max_hits,
        }
    )
)

# POST /verify admin 완화 — IP별 1시간 윈도우 200회, 장기차단 없음.
_admin_verify_limiter = SlidingWindowLimiter(
    _settings.admin_rate_window_seconds,
    _settings.admin_rate_max_hits,
    _settings.ratelimit_sweep_seconds,
)


async def rate_limit(request: Request) -> None:
    """글로벌 레이트리밋 의존성(예: GET /result). 차단 시 RateLimited 발생."""
    limiter.check(client_ip(request))


async def verify_rate_limit(
    request: Request,
    user: dict | None = Depends(get_current_user_optional),
) -> None:
    """POST /verify 전용 티어 레이트리밋(IP 기준). 차단 시 RateLimited 발생.

    admin(JWT sub == admin_id) → admin 완화 한도(장기차단 없음),
    그 외(비로그인 등) → verify 한도 + 에스컬레이션 차단.
    """
    ip = client_ip(request)
    if user and user.get("sub") == _settings.admin_id:
        _admin_verify_limiter.check(ip)
    else:
        _anon_verify_limiter.check(ip)


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
