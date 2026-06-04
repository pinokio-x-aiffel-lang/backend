from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    user_id: str
    password: str


class RegisterRequest(BaseModel):
    user_id: str
    password: str
    name: str | None = None


class UserInfo(BaseModel):
    id: str
    user_id: str
    name: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo | None = None
