"""자체 ID/PW 인증 라우터.

POST /auth/register  — 회원가입
POST /auth/login     — 로그인 → JWT 발급
GET  /auth/me        — 현재 사용자 정보
POST /auth/logout    — 로그아웃 (best-effort, 멱등)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.database import get_db
from src.auth.denylist import revoke
from src.auth.deps import get_current_user
from src.auth.jwt_handler import create_access_token, decode_access_token
from src.auth.models import User
from src.auth.password import hash_password, verify_password
from src.auth.schemas import LoginRequest, LoginResponse, RegisterRequest, UserInfo
from src.config import load_settings

router = APIRouter(prefix="/auth", tags=["auth"])

_s = load_settings()
# 로그아웃은 토큰이 없어도 통과(멱등)해야 하므로 auto_error=False 의 선택적 Bearer.
_optional_bearer = HTTPBearer(auto_error=False)


def _make_response(user_id: str, name: str | None) -> LoginResponse:
    token = create_access_token(user_id, name)
    return LoginResponse(
        access_token=token,
        user=UserInfo(id=user_id, user_id=user_id, name=name),
    )


def _admin_ok(user_id: str, password: str) -> bool:
    """서버에 저장된 단일 admin 자격증명과 일치하는지 검증."""
    if not _s.admin_password_hash:          # 미설정이면 로그인 차단
        return False
    if user_id != _s.admin_id:
        return False
    return verify_password(password, _s.admin_password_hash)


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    """회원가입. user_id 중복이면 409."""
    result = await db.execute(select(User).where(User.user_id == body.user_id))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="이미 사용 중인 아이디입니다.")

    user = User(
        user_id=body.user_id,
        hashed_password=hash_password(body.password),
        name=body.name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _make_response(user.user_id, user.name)


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    """로그인. 서버에 저장된 admin 자격증명과 일치할 때만 통과, 실패 시 401."""
    if not _admin_ok(body.user_id, body.password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    return _make_response(_s.admin_id, _s.admin_name)


@router.get("/me")
async def me(payload: dict = Depends(get_current_user)) -> dict:
    """현재 로그인된 사용자 정보."""
    return {"user_id": payload["sub"], "name": payload.get("name")}


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> dict:
    """로그아웃 (best-effort, 멱등) — auth-spec.md §5-3.

    토큰이 있으면 그 jti 를 in-memory denylist 에 등록해 만료 전이라도 무효화한다
    (이후 get_current_user 가 401 로 거부). 인증이 없거나 토큰이 만료/무효여도
    막지 않고 항상 200 을 반환한다. 204 가 아닌 JSON body 로 응답한다(프론트
    apiFetch 가 res.json() 을 호출하므로 빈 본문이면 에러).

    NOTE: denylist 는 in-memory 라 앱 재시작/재배포 시 사라진다(영속·공유 필요 시
    Redis/Postgres 로 src/auth/denylist.py 교체) — auth-spec.md §5-2 참고.
    """
    if credentials:
        payload = decode_access_token(credentials.credentials)
        jti, exp = payload.get("jti"), payload.get("exp")
        if jti and exp:
            revoke(jti, float(exp))
    return {"ok": True}
