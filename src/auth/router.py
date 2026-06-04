"""자체 ID/PW 인증 라우터.

POST /auth/register  — 회원가입
POST /auth/login     — 로그인 → JWT 발급
GET  /auth/me        — 현재 사용자 정보
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

router = APIRouter(prefix="/auth", tags=["auth"])


def _make_response(user: User) -> LoginResponse:
    token = create_access_token(user.user_id, user.name)
    return LoginResponse(
        access_token=token,
        user=UserInfo(id=user.user_id, user_id=user.user_id, name=user.name),
    )


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
    return _make_response(user)


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    """로그인. 실패 시 401."""
    result = await db.execute(select(User).where(User.user_id == body.user_id))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    return _make_response(user)


@router.get("/me")
async def me(payload: dict = Depends(get_current_user)) -> dict:
    """현재 로그인된 사용자 정보."""
    return {"user_id": payload["sub"], "name": payload.get("name")}
