"""자체 ID/PW 인증 라우터.

POST /auth/register  — 회원가입
POST /auth/login     — 로그인 → JWT 발급
GET  /auth/me        — 현재 사용자 정보
POST /auth/logout    — 로그아웃 (best-effort, 멱등)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.database import get_db
from src.auth.deps import get_current_user
from src.auth.jwt_handler import create_access_token
from src.auth.models import User
from src.auth.password import hash_password, verify_password
from src.auth.schemas import LoginRequest, LoginResponse, RegisterRequest, UserInfo
from src.config import load_settings

router = APIRouter(prefix="/auth", tags=["auth"])

_s = load_settings()


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
async def logout() -> dict:
    """로그아웃 (best-effort, 멱등) — auth-spec.md §5-3.

    stateless JWT 라 서버 측 토큰 폐기는 없다. 프론트(auth.ts)가 클라이언트에
    저장된 토큰을 제거한다. 인증이 없거나 토큰이 만료/무효여도 막지 않고 항상
    200 을 반환한다(로그아웃은 항상 성공 처리). 204 가 아닌 JSON body 로 응답한다
    (프론트 apiFetch 가 res.json() 을 호출하므로 빈 본문이면 에러).

    NOTE: 발급된 토큰은 만료까지 서버에서 유효하다(즉시 무효화 불가). 즉시 폐기가
    필요하면 JWT 에 jti 추가 + denylist(Redis) 도입 — auth-spec.md §5-2 참고.
    """
    return {"ok": True}
