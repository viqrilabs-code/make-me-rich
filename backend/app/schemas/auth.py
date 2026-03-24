from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class SignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    timezone: str = Field(default="Asia/Kolkata", min_length=3, max_length=64)


class UserResponse(BaseModel):
    username: str
    timezone: str


class AuthResponse(BaseModel):
    authenticated: bool
    user: UserResponse | None = None
    has_user: bool = False
    signup_allowed: bool = False
